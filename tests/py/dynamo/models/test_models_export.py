import unittest

import pytest
import timm
import torch
import torch_tensorrt as torchtrt
import torchvision.models as models
from torch_tensorrt.dynamo.utils import COSINE_THRESHOLD, cosine_similarity
from transformers import BertModel
from transformers.utils.fx import symbolic_trace as transformers_trace

assertions = unittest.TestCase()


@pytest.mark.unit
def test_resnet18(ir):
    model = models.resnet18(pretrained=True).eval().to("cuda")
    input = torch.randn((1, 3, 224, 224)).to("cuda")

    compile_spec = {
        "inputs": [
            torchtrt.Input(
                input.shape, dtype=torch.float, format=torch.contiguous_format
            )
        ],
        "device": torchtrt.Device("cuda:0"),
        "enabled_precisions": {torch.float},
        "ir": ir,
        "pass_through_build_failures": True,
        "optimization_level": 1,
        "min_block_size": 8,
        "ir": "dynamo",
    }

    trt_mod = torchtrt.compile(model, **compile_spec)
    cos_sim = cosine_similarity(model(input), trt_mod(input)[0])
    assertions.assertTrue(
        cos_sim > COSINE_THRESHOLD,
        msg=f"Resnet18 TRT outputs don't match with the original model. Cosine sim score: {cos_sim} Threshold: {COSINE_THRESHOLD}",
    )

    # Clean up model env
    torch._dynamo.reset()


@pytest.mark.unit
def test_mobilenet_v2(ir):
    model = models.mobilenet_v2(pretrained=True).eval().to("cuda")
    input = torch.randn((1, 3, 224, 224)).to("cuda")

    compile_spec = {
        "inputs": [
            torchtrt.Input(
                input.shape, dtype=torch.float, format=torch.contiguous_format
            )
        ],
        "device": torchtrt.Device("cuda:0"),
        "enabled_precisions": {torch.float},
        "ir": ir,
        "pass_through_build_failures": True,
        "optimization_level": 1,
        "min_block_size": 8,
        "ir": "dynamo",
    }

    trt_mod = torchtrt.compile(model, **compile_spec)
    cos_sim = cosine_similarity(model(input), trt_mod(input)[0])
    assertions.assertTrue(
        cos_sim > COSINE_THRESHOLD,
        msg=f"Mobilenet v2 TRT outputs don't match with the original model. Cosine sim score: {cos_sim} Threshold: {COSINE_THRESHOLD}",
    )

    # Clean up model env
    torch._dynamo.reset()


@pytest.mark.unit
def test_efficientnet_b0(ir):
    model = timm.create_model("efficientnet_b0", pretrained=True).eval().to("cuda")
    input = torch.randn((1, 3, 224, 224)).to("cuda")

    compile_spec = {
        "inputs": [
            torchtrt.Input(
                input.shape, dtype=torch.float, format=torch.contiguous_format
            )
        ],
        "device": torchtrt.Device("cuda:0"),
        "enabled_precisions": {torch.float},
        "ir": ir,
        "pass_through_build_failures": True,
        "optimization_level": 1,
        "min_block_size": 8,
        "ir": "dynamo",
    }

    trt_mod = torchtrt.compile(model, **compile_spec)
    cos_sim = cosine_similarity(model(input), trt_mod(input)[0])
    assertions.assertTrue(
        cos_sim > COSINE_THRESHOLD,
        msg=f"EfficientNet-B0 TRT outputs don't match with the original model. Cosine sim score: {cos_sim} Threshold: {COSINE_THRESHOLD}",
    )

    # Clean up model env
    torch._dynamo.reset()


@pytest.mark.unit
def test_bert_base_uncased(ir):
    model = BertModel.from_pretrained("bert-base-uncased").cuda().eval()
    input = torch.randint(0, 1, (1, 14), dtype=torch.int32).to("cuda")
    input2 = torch.randint(0, 1, (1, 14), dtype=torch.int32).to("cuda")
    # model = (
    #     transformers_trace(model, input_names=["input_ids", "attention_mask"])
    #     .eval()
    #     .cuda()
    # )

    compile_spec = {
        "inputs": [
            torchtrt.Input(
                input.shape,
                dtype=input.dtype,
                format=torch.contiguous_format,
            ),
            torchtrt.Input(
                input.shape,
                dtype=input.dtype,
                format=torch.contiguous_format,
            ),
        ],
        "device": torchtrt.Device("cuda:0"),
        "enabled_precisions": {torch.float},
        "truncate_long_and_double": True,
        "ir": ir,
        "min_block_size": 15,
    }
    trt_mod = torchtrt.compile(model, **compile_spec)
    model_outputs = model(input, input2)
    trt_model_outputs = trt_mod(input, input2)
    assertions.assertTrue(
        len(model_outputs) == len(trt_model_outputs),
        msg=f"Number of outputs for BERT model compilation is different with Pytorch {len(model_outputs)} and TensorRT {len(trt_model_outputs)}. Please check the compilation.",
    )

    for key, _ in model_outputs.items():
        out, trt_out = model_outputs[key], trt_model_outputs[key]
        cos_sim = cosine_similarity(out, trt_out)
        assertions.assertTrue(
            cos_sim > COSINE_THRESHOLD,
            msg=f"HF BERT base-uncased TRT outputs don't match with the original model. Cosine sim score: {cos_sim} Threshold: {COSINE_THRESHOLD}",
        )

    # Clean up model env
    torch._dynamo.reset()


@pytest.mark.unit
def test_resnet18_half(ir):
    model = models.resnet18(pretrained=True).eval().to("cuda").half()
    input = torch.randn((1, 3, 224, 224)).to("cuda").half()

    compile_spec = {
        "inputs": [
            torchtrt.Input(
                input.shape, dtype=torch.half, format=torch.contiguous_format
            )
        ],
        "device": torchtrt.Device("cuda:0"),
        "enabled_precisions": {torch.half},
        "ir": ir,
        "pass_through_build_failures": True,
        "optimization_level": 1,
        "min_block_size": 8,
        "ir": "dynamo",
    }

    trt_mod = torchtrt.compile(model, **compile_spec)
    cos_sim = cosine_similarity(model(input), trt_mod(input)[0])
    assertions.assertTrue(
        cos_sim > COSINE_THRESHOLD,
        msg=f"Resnet18 Half TRT outputs don't match with the original model. Cosine sim score: {cos_sim} Threshold: {COSINE_THRESHOLD}",
    )

    # Clean up model env
    torch._dynamo.reset()
