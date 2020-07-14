from contextlib import contextmanager

import cupy
import numpy as np
import pandas as pd
from pandas.util import testing as tm

import cudf
from cudf._lib.null_mask import bitmask_allocation_size_bytes
from cudf.utils import dtypes as dtypeutils

supported_numpy_dtypes = [
    "bool",
    "int8",
    "int16",
    "int32",
    "int64",
    "float32",
    "float64",
    "datetime64[ms]",
    "datetime64[us]",
]

SIGNED_INTEGER_TYPES = sorted(list(dtypeutils.SIGNED_INTEGER_TYPES))
UNSIGNED_TYPES = sorted(list(dtypeutils.UNSIGNED_TYPES))
INTEGER_TYPES = sorted(list(dtypeutils.INTEGER_TYPES))
FLOAT_TYPES = sorted(list(dtypeutils.FLOAT_TYPES))
SIGNED_TYPES = sorted(list(dtypeutils.SIGNED_TYPES))
NUMERIC_TYPES = sorted(list(dtypeutils.NUMERIC_TYPES))
DATETIME_TYPES = sorted(list(dtypeutils.DATETIME_TYPES))
OTHER_TYPES = sorted(list(dtypeutils.OTHER_TYPES))
ALL_TYPES = sorted(list(dtypeutils.ALL_TYPES))


def random_bitmask(size):
    """
    Parameters
    ----------
    size : int
        number of bits
    """
    sz = bitmask_allocation_size_bytes(size)
    data = np.random.randint(0, 255, dtype="u1", size=sz)
    return data.view("i1")


def expand_bits_to_bytes(arr):
    def fix_binary(bstr):
        bstr = bstr[2:]
        diff = 8 - len(bstr)
        return ("0" * diff + bstr)[::-1]

    ba = bytearray(arr.data)
    return list(map(int, "".join(map(fix_binary, map(bin, ba)))))


def count_zero(arr):
    arr = np.asarray(arr)
    return np.count_nonzero(arr == 0)


def assert_eq(left, right, allow_nullable_pd_types=True, **kwargs):
    """ Assert that two cudf-like things are equivalent

    This equality test works for pandas/cudf dataframes/series/indexes/scalars
    in the same way, and so makes it easier to perform parametrized testing
    without switching between assert_frame_equal/assert_series_equal/...
    functions.
    """
    __tracebackhide__ = True

    if hasattr(left, "to_pandas"):
        left = left.to_pandas()
    if hasattr(right, "to_pandas"):
        right = right.to_pandas()
    if isinstance(left, cupy.ndarray):
        left = cupy.asnumpy(left)
    if isinstance(right, cupy.ndarray):
        right = cupy.asnumpy(right)
    if (
        allow_nullable_pd_types
        and isinstance(left, (pd.Series, pd.DataFrame))
        and left.__class__ == right.__class__
    ):
        left = maybe_demote_dtypes(left)
        right = maybe_demote_dtypes(right)
    if isinstance(left, pd.DataFrame):
        tm.assert_frame_equal(left, right, **kwargs)
    elif isinstance(left, pd.Series):
        tm.assert_series_equal(left, right, **kwargs)
    elif isinstance(left, pd.Index):
        tm.assert_index_equal(left, right, **kwargs)
    elif isinstance(left, np.ndarray) and isinstance(right, np.ndarray):
        if np.issubdtype(left.dtype, np.floating) and np.issubdtype(
            right.dtype, np.floating
        ):
            assert np.allclose(left, right, equal_nan=True)
        else:
            assert np.array_equal(left, right)
    else:
        if left == right:
            return True
        else:
            if np.isnan(left):
                assert np.isnan(right)
            else:
                assert np.allclose(left, right, equal_nan=True)
    return True

def demote_series_dtype(sr):
    """ Demote a pandas nullable extension dtype into
    a non-nullable numpy type, filling with the appropriate
    NA value
    """
    in_dtype = sr.dtype
    dtype_map = {v:k for k, v in dtypeutils.cudf_dtypes_to_pandas_dtypes.items()}
    out_dtype = dtype_map.get(sr.dtype, sr.dtype)

    if out_dtype.kind in ('i', 'u'):
        min_int = np.iinfo(out_dtype).min
        out_sr = sr.fillna(min_int)
        out_sr = out_sr.astype(out_dtype)
    elif out_dtype.kind in ('O', 'b'):
        if out_dtype.kind == 'b':
            out_dtype = np.dtype('O')
        out_sr = sr.astype(out_dtype)
        # instantiating pandas str/bool series with None still gets object
        # does NOT default to extension with pd.NA yet
        out_sr[sr.isnull()] = None        
    else:
        out_sr = sr
    return out_sr


def maybe_demote_dtypes(obj):
    if isinstance(obj, pd.Series):
        return demote_series_dtype(obj)
    elif isinstance(obj, pd.DataFrame):
        for col in obj.columns:
            obj[col] = demote_series_dtype(obj[col])
    return obj


def assert_neq(left, right, **kwargs):
    __tracebackhide__ = True
    try:
        assert_eq(left, right, **kwargs)
    except AssertionError:
        pass
    else:
        raise AssertionError


def gen_rand(dtype, size, **kwargs):
    dtype = np.dtype(dtype)
    if dtype.kind == "f":
        res = np.random.random(size=size).astype(dtype)
        if kwargs.get("positive_only", False):
            return res
        else:
            return res * 2 - 1
    elif dtype == np.int8 or dtype == np.int16:
        low = kwargs.get("low", -32)
        high = kwargs.get("high", 32)
        return np.random.randint(low=low, high=high, size=size).astype(dtype)
    elif dtype.kind == "i":
        low = kwargs.get("low", -10000)
        high = kwargs.get("high", 10000)
        return np.random.randint(low=low, high=high, size=size).astype(dtype)
    elif dtype == np.uint8 or dtype == np.uint16:
        low = kwargs.get("low", 0)
        high = kwargs.get("high", 32)
        return np.random.randint(low=low, high=high, size=size).astype(dtype)
    elif dtype.kind == "u":
        low = kwargs.get("low", 0)
        high = kwargs.get("high", 128)
        return np.random.randint(low=low, high=high, size=size).astype(dtype)
    elif dtype.kind == "b":
        low = kwargs.get("low", 0)
        high = kwargs.get("high", 1)
        return np.random.randint(low=low, high=high, size=size).astype(np.bool)
    raise NotImplementedError("dtype.kind={}".format(dtype.kind))


def gen_rand_series(dtype, size, **kwargs):
    values = gen_rand(dtype, size, **kwargs)
    if kwargs.get("has_nulls", False):
        return cudf.Series.from_masked_array(values, random_bitmask(size))

    return cudf.Series(values)


@contextmanager
def does_not_raise():
    yield
