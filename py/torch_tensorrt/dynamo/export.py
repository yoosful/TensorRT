import copy
import operator
from typing import Any, Dict, Sequence, Tuple, Union, cast

import torch
from torch._guards import detect_fake_mode
from torch._subclasses.fake_tensor import FakeTensor
from torch.export import ExportedProgram, ExportGraphSignature
from torch.export.exported_program import (
    InputKind,
    InputSpec,
    OutputKind,
    OutputSpec,
    TensorArgument,
)
from torch_tensorrt.dynamo import partitioning


def transform(
    gm: torch.fx.GraphModule, inputs: Sequence[torch.Tensor]
) -> torch.fx.GraphModule:
    # Run shape analysis
    _, outputs_map = partitioning.run_shape_analysis(gm, inputs)

    # Inline TensorRT submodules
    inline_trt_modules(gm, outputs_map)

    # Inline pytorch submodules
    inline_torch_modules(gm)

    # Lift constant buffers and parameters in the graph
    # torch.export serialization expects them to be lifted
    lift_constant_pass(gm)

    # Clean the graph
    gm.delete_all_unused_submodules()
    gm.graph.eliminate_dead_code()
    gm.graph.lint()

    return gm


def lift_constant_pass(trt_gm: torch.fx.GraphModule) -> torch.fx.GraphModule:
    fake_mode = detect_fake_mode(
        tuple(
            node.meta["val"] for node in trt_gm.graph.nodes if node.op == "placeholder"
        )
    )

    first_user_input = None
    for node in trt_gm.graph.nodes:
        if node.op == "placeholder":
            first_user_input = node
            break

    for node in trt_gm.graph.nodes:
        if node.op == "get_attr":
            constant_tensor = getattr(trt_gm, node.target)
            with trt_gm.graph.inserting_before(first_user_input):
                const_placeholder_node = trt_gm.graph.placeholder(node.target)
                const_placeholder_node.meta = copy.deepcopy(node.meta)
                const_placeholder_node.meta["val"] = fake_mode.from_tensor(
                    constant_tensor
                )
                node.replace_all_uses_with(const_placeholder_node)
                trt_gm.graph.erase_node(node)

    trt_gm.graph.eliminate_dead_code()
    trt_gm.graph.lint()
    return trt_gm


def get_duplicate_nodes(
    gm: torch.fx.GraphModule, submodule: torch.fx.GraphModule
) -> Tuple[Sequence[Any], Sequence[Any]]:
    """
    We check if there are duplicate nodes when we copy submodule graph into gm.
    Handle the case where the subgraph input placeholders are same as
    gm placeholders. This happens when the first submodule in the graph is
    a pytorch submodule
    """
    submodule_placeholder_inputs = [
        node for node in submodule.graph.nodes if node.op == "placeholder"
    ]
    submodule_input_node_names = [node.name for node in submodule_placeholder_inputs]
    gm_node_names = [node.name for node in gm.graph.nodes]
    submodule_duplicate_inputs = [
        node for node in submodule_placeholder_inputs if node.name in gm_node_names
    ]
    gm_duplicate_inputs = [
        node for node in gm.graph.nodes if node.name in submodule_input_node_names
    ]
    return submodule_duplicate_inputs, gm_duplicate_inputs


def inline_torch_modules(gm: torch.fx.GraphModule) -> torch.fx.GraphModule:
    """
    Inline a submodule within the parent graph (gm). All `call_module` nodes
    should be replaced by their submodule nodes.
    """
    # Clean the graph
    gm.graph.eliminate_dead_code()
    gm.graph.lint()

    for gm_node in gm.graph.nodes:
        if gm_node.op == "call_module" and "_run_on_gpu" in gm_node.name:
            submodule = getattr(gm, gm_node.name)
            with gm.graph.inserting_before(gm_node):
                # Get inputs of submodule node which are most likely outputs of a previous TRT node
                # or a placeholder of the main graph
                submodule_inputs = gm_node.args

                submodule_duplicate_inputs, gm_duplicate_inputs = get_duplicate_nodes(
                    gm, submodule
                )
                assert len(submodule_duplicate_inputs) == len(gm_duplicate_inputs)
                # Avoid creating new copies of duplicate inputs by creating a mapping
                val_map = {}
                for i in range(len(submodule_duplicate_inputs)):
                    val_map[submodule_duplicate_inputs[i]] = gm_duplicate_inputs[i]

                # Copy all nodes in the submodule into gm and
                # store the output node of this submodule which is now present in gm

                submodule_output = gm.graph.graph_copy(submodule.graph, val_map)

                # Get their references (since we copied) in the parent graph (gm)
                if len(submodule_duplicate_inputs) == 0:
                    submodule_placeholder_input_names = [
                        node.name
                        for node in submodule.graph.nodes
                        if node.op == "placeholder"
                    ]
                    gm_added_placeholder_inputs = [
                        node
                        for node in gm.graph.nodes
                        if node.name in submodule_placeholder_input_names
                    ]

                    assert len(submodule_inputs) == len(gm_added_placeholder_inputs)

                    # Replace the added placeholder inputs with original inputs to this submodule node
                    for idx in range(len(gm_added_placeholder_inputs)):
                        gm_added_placeholder_inputs[idx].replace_all_uses_with(
                            submodule_inputs[idx]
                        )

                    # Erase the placeholder input nodes in the gm
                    for idx in range(len(gm_added_placeholder_inputs)):
                        gm.graph.erase_node(gm_added_placeholder_inputs[idx])

                # Replace the pytorch submodule node (call_module) with the inlined subgraph output
                gm_node.replace_all_uses_with(submodule_output)

                # copy the attributes of the submodule into gm (graph_copy doesn't do this)
                copy_submodule_attributes(submodule, gm, gm_node.name)

            # Erase the pytorch submodule (call_module) node
            gm.graph.erase_node(gm_node)

    return gm


def copy_submodule_attributes(
    submodule: torch.fx.GraphModule, gm: torch.fx.GraphModule, submod_name: str
) -> None:
    """
    Copy the getattr attriibutes from submodule to parent module gm.
    The graph_copy call doesn't do this for us unfortunately.
    """
    for param in gm.named_parameters():
        if param[0].startswith(submod_name + "."):
            attr_name = param[0].replace(submod_name + ".", "")
            gm.register_parameter(attr_name, param[1])

    for buffer in gm.named_buffers():
        if buffer[0].startswith(submod_name + "."):
            attr_name = buffer[0].replace(submod_name + ".", "")
            gm.register_buffer(attr_name, buffer[1])


def create_trt_exp_program(
    gm: torch.fx.GraphModule,
    state_dict: Dict[str, Union[torch.Tensor, torch.nn.Parameter]],
) -> ExportedProgram:
    """Creates a new Exported Program. This function takes an torch.fx.GraphModule which has TRT engines
    and constructs an Exported Program object with the new IO node names, call_spec and state_dict
    """
    input_nodes = [node for node in gm.graph.nodes if node.op == "placeholder"]
    output_nodes = [node for node in gm.graph.nodes if node.op == "output"]

    input_specs = [
        InputSpec(InputKind.USER_INPUT, TensorArgument(name=node.name), node.target)
        for node in input_nodes
    ]
    output_specs = [
        OutputSpec(OutputKind.USER_OUTPUT, TensorArgument(name=node.name), node.target)
        for node in output_nodes
    ]

    trt_graph_signature = ExportGraphSignature(
        input_specs=input_specs, output_specs=output_specs
    )

    trt_exp_program = ExportedProgram(
        gm, gm.graph, trt_graph_signature, state_dict, {}, [], [], []
    )

    return trt_exp_program


def inline_trt_modules(
    gm: torch.fx.GraphModule, outputs_map: Dict[Any, Sequence[Any]]
) -> torch.fx.GraphModule:
    """
    Replace TRT submodules with trt engine nodes.
    """
    for name, _ in gm.named_children():
        if "_run_on_acc" not in name:
            continue
        # Get the TRT submodule
        trt_module = getattr(gm, name)

        # Ensure the trt module node in the main graph (gm) has inputs
        trt_module_node = [node for node in gm.graph.nodes if node.name == name]
        assert trt_module_node
        trt_module_node = trt_module_node[0]
        assert trt_module_node.args

        num_outputs = len(outputs_map[trt_module_node.name])
        # Insert a call_function node to perform inference on TRT engine
        with gm.graph.inserting_before(trt_module_node):
            trt_node = gm.graph.call_function(
                torch.ops.tensorrt.execute_engine.default,
                (trt_module_node.args, trt_module.engine),
            )
            trt_node.meta["val"] = []
            # Generate meta data for TRT node (a FakeTensor with corresponding output shape)
            for idx in range(num_outputs):
                trt_node.meta["val"].append(
                    cast(
                        FakeTensor,
                        torch.empty_strided(
                            tuple(outputs_map[trt_module_node.name][idx]),
                            tuple([1] * len(outputs_map[trt_module_node.name][idx])),
                        ),
                    )
                )

        if num_outputs == 1:
            # Insert getitem nodes as outputs (for export serialization to work)
            with gm.graph.inserting_after(trt_node):
                getitem_output = gm.graph.call_function(operator.getitem, (trt_node, 0))
                getitem_output.meta["val"] = trt_node.meta["val"][0]
            trt_module_node.replace_all_uses_with(getitem_output)
        else:
            # Multiple outputs case:
            # Replace uses of submodule with the trt_node.
            # getitem nodes are already added inherently by the partitioner
            trt_module_node.replace_all_uses_with(trt_node)

        # Erase the TRT submodule (call_module) node.
        gm.graph.erase_node(trt_module_node)

    return gm
