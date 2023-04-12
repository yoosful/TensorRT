import torch
import torch_tensorrt.fx.tracer.acc_tracer.acc_ops as acc_ops
from parameterized import parameterized
from torch.testing._internal.common_utils import run_tests
from torch_tensorrt.dynamo.fx_ts_compat.tools.common_fx2trt import (
    AccTestCase,
    InputTensorSpec,
)


class TestLtConverter(AccTestCase):
    @parameterized.expand(
        [
            ("rand_2d", torch.randn(3, 4), torch.randn(3, 4)),
            ("rand_3d", torch.randn(3, 4, 5), torch.randn(3, 4, 5)),
            ("rand_4d", torch.randn(3, 4, 5, 6), torch.randn(3, 4, 5, 6)),
            (
                "rand_2d_int_bool",
                (torch.randn(3, 4)).to(torch.int),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_bool",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_int",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.int),
            ),
        ]
    )
    def test_lt(self, _, input, other):
        class Lt(torch.nn.Module):
            def forward(self, x, y):
                mask = torch.lt(x, y)
                return x.masked_fill(mask, 5)

        inputs = [
            input,
            other,
        ]
        self.run_test(
            Lt(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestLtMethodConverter(AccTestCase):
    @parameterized.expand(
        [
            ("rand_2d", torch.randn(3, 4), torch.randn(3, 4)),
            ("rand_3d", torch.randn(3, 4, 5), torch.randn(3, 4, 5)),
            ("rand_4d", torch.randn(3, 4, 5, 6), torch.randn(3, 4, 5, 6)),
            (
                "rand_2d_int_bool",
                torch.randn(3, 4).to(torch.int),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_bool",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_int",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.int),
            ),
        ]
    )
    def test_lt(self, _, input, other):
        class Lt(torch.nn.Module):
            def forward(self, x, y):
                mask = x.lt(y)
                return x.masked_fill(mask, 5)

        inputs = [
            input,
            other,
        ]
        self.run_test(
            Lt(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestLtOperatorConverter(AccTestCase):
    @parameterized.expand(
        [
            ("rand_2d", torch.randn(3, 4), torch.randn(3, 4)),
            ("rand_3d", torch.randn(3, 4, 5), torch.randn(3, 4, 5)),
            ("rand_4d", torch.randn(3, 4, 5, 6), torch.randn(3, 4, 5, 6)),
            (
                "rand_2d_int_bool",
                torch.randn(3, 4).to(torch.int),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_bool",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_int",
                torch.randn(3, 4).to(torch.float),
                torch.zeros(3, 4).to(torch.int),
            ),
        ]
    )
    def test_lt(self, _, input, other):
        class Lt(torch.nn.Module):
            def forward(self, x, y):
                mask = x < y
                return x.masked_fill(mask, 5)

        inputs = [
            input,
            other,
        ]
        self.run_test(
            Lt(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestEqOperatorSimpleConverter(AccTestCase):
    @parameterized.expand(
        [
            ("rand_2d_float_bool", torch.randn(3, 4), torch.randn(3, 4).to(torch.bool)),
            (
                "rand_2d_int_bool",
                torch.randn(3, 4).to(torch.int),
                torch.randn(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_bool_bool",
                torch.randn(3, 4).to(torch.bool),
                torch.randn(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_int",
                torch.randn(3, 4).to(torch.float),
                torch.randn(3, 4).to(torch.int),
            ),
            (
                "rand_2d_float_single_bool",
                torch.randn(3, 4),
                torch.tensor(0).to(torch.bool),
            ),
            (
                "rand_2d_int_single_bool",
                torch.randn(3, 4).to(torch.int),
                torch.tensor(0).to(torch.bool),
            ),
            (
                "rand_2d_bool_single_bool",
                torch.randn(3, 4).to(torch.bool),
                torch.tensor(0).to(torch.bool),
            ),
        ]
    )
    def test_eq(self, _, input, other):
        class Eq(torch.nn.Module):
            def forward(self, x, y):
                return x < y

        inputs = [
            input,
            other,
        ]
        self.run_test(
            Eq(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestEqOperatorSimpleConverterWithDynamicShape(AccTestCase):
    def test_eq(self):
        class Eq(torch.nn.Module):
            def forward(self, x, y):
                return x < y

        input_specs = [
            InputTensorSpec(
                shape=(-1, -1, -1, -1),
                dtype=torch.float32,
                shape_ranges=[((1, 1, 1, 1), (2, 3, 4, 5), (2, 3, 10, 10))],
            ),
            InputTensorSpec(
                shape=(-1, -1, -1, -1),
                dtype=torch.float32,
                shape_ranges=[((1, 1, 1, 1), (2, 3, 4, 5), (2, 3, 10, 10))],
            ),
        ]

        self.run_test_with_dynamic_shape(Eq(), input_specs, expected_ops={acc_ops.lt})


class TestEqOperatorConstantConverter(AccTestCase):
    @parameterized.expand(
        [
            ("rand_2d_float_bool", torch.randn(3, 4), torch.randn(3, 4).to(torch.bool)),
            (
                "rand_2d_int_bool",
                torch.randn(3, 4).to(torch.int),
                torch.randn(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_bool_bool",
                torch.randn(3, 4).to(torch.bool),
                torch.randn(3, 4).to(torch.bool),
            ),
            (
                "rand_2d_float_int",
                torch.randn(3, 4).to(torch.float),
                torch.randn(3, 4).to(torch.int),
            ),
            ("rand_2d_float_single_bool", torch.randn(3, 4), False),
            ("rand_2d_int_single_bool", torch.randn(3, 4).to(torch.int), False),
            ("rand_2d_bool_single_bool", torch.randn(3, 4).to(torch.bool), False),
        ]
    )
    def test_eq(self, _, input, other):
        class Eq(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.other = other

            def forward(self, x):
                return x < self.other

        inputs = [
            input,
        ]
        self.run_test(
            Eq(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestConstInputConverter(AccTestCase):
    def test_lt(self):
        class Lt(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, x):
                return x.shape[0] < 4

        input = torch.randn(3, 4)
        inputs = [
            input,
        ]
        self.run_test(
            Lt(), inputs, expected_ops={acc_ops.lt}, test_implicit_batch_dim=False
        )


class TestConstInputConverterWithDynamicShape(AccTestCase):
    def test_lt(self):
        class Lt(torch.nn.Module):
            def __init__(self):
                super().__init__()

            def forward(self, x):
                return x.shape[0] < 4

        input_specs = [
            InputTensorSpec(
                shape=(-1, -1, -1, -1),
                dtype=torch.float32,
                shape_ranges=[((1, 1, 1, 1), (2, 3, 4, 5), (2, 3, 10, 10))],
            )
        ]

        self.run_test_with_dynamic_shape(Lt(), input_specs, expected_ops={acc_ops.lt})


if __name__ == "__main__":
    run_tests()
