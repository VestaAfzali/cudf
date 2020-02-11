import numpy as np
import pandas as pd
import pytest

from cudf import (
    melt as cudf_melt,
    interleave_columns as cudf_interleave_columns,
    tile as cudf_tile
)
from cudf.core import DataFrame
from cudf.tests.utils import assert_eq


@pytest.mark.parametrize("num_id_vars", [0, 1, 2, 10])
@pytest.mark.parametrize("num_value_vars", [0, 1, 2, 10])
@pytest.mark.parametrize("num_rows", [1, 2, 1000])
@pytest.mark.parametrize(
    "dtype",
    [
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "datetime64[ms]",
    ],
)
@pytest.mark.parametrize("nulls", ["none", "some", "all"])
def test_melt(nulls, num_id_vars, num_value_vars, num_rows, dtype):
    if dtype not in ["float32", "float64"] and nulls in ["some", "all"]:
        pytest.skip(msg="nulls not supported in dtype: " + dtype)

    pdf = pd.DataFrame()
    id_vars = []
    for i in range(num_id_vars):
        colname = "id" + str(i)
        data = np.random.randint(0, 26, num_rows).astype(dtype)
        if nulls == "some":
            idx = np.random.choice(
                num_rows, size=int(num_rows / 2), replace=False
            )
            data[idx] = np.nan
        elif nulls == "all":
            data[:] = np.nan
        pdf[colname] = data
        id_vars.append(colname)

    value_vars = []
    for i in range(num_value_vars):
        colname = "val" + str(i)
        data = np.random.randint(0, 26, num_rows).astype(dtype)
        if nulls == "some":
            idx = np.random.choice(
                num_rows, size=int(num_rows / 2), replace=False
            )
            data[idx] = np.nan
        elif nulls == "all":
            data[:] = np.nan
        pdf[colname] = data
        value_vars.append(colname)

    gdf = DataFrame.from_pandas(pdf)

    got = cudf_melt(frame=gdf, id_vars=id_vars, value_vars=value_vars)
    got_from_melt_method = gdf.melt(id_vars=id_vars, value_vars=value_vars)

    expect = pd.melt(frame=pdf, id_vars=id_vars, value_vars=value_vars)
    # pandas' melt makes the 'variable' column of 'object' type (string)
    # cuDF's melt makes it Categorical because it doesn't support strings
    expect["variable"] = expect["variable"].astype("category")

    pd.testing.assert_frame_equal(expect, got.to_pandas())

    pd.testing.assert_frame_equal(expect, got_from_melt_method.to_pandas())


@pytest.mark.parametrize("num_cols", [1, 2, 10])
@pytest.mark.parametrize("num_rows", [1, 2, 1000])
@pytest.mark.parametrize(
    "dtype",
    [
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "datetime64[ms]",
        "str",
    ],
)
@pytest.mark.parametrize("nulls", ["none", "some"])
def test_df_stack(nulls, num_cols, num_rows, dtype):
    if dtype not in ["float32", "float64"] and nulls in ["some"]:
        pytest.skip(msg="nulls not supported in dtype: " + dtype)

    pdf = pd.DataFrame()
    for i in range(num_cols):
        colname = str(i)
        data = np.random.randint(0, 26, num_rows).astype(dtype)
        if nulls == "some":
            idx = np.random.choice(
                num_rows, size=int(num_rows / 2), replace=False
            )
            data[idx] = np.nan
        pdf[colname] = data

    gdf = DataFrame.from_pandas(pdf)

    got = gdf.stack()

    expect = pdf.stack()
    if {None} == set(expect.index.names):
        expect.rename_axis(
            list(range(0, len(expect.index.names))), inplace=True
        )

    assert_eq(expect, got)
    pass

@pytest.mark.parametrize("num_rows", [1, 2, 1000])
@pytest.mark.parametrize("num_cols", [1, 2, 10])
@pytest.mark.parametrize(
    "dtype",
    [
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "datetime64[ms]",
        "str",
    ],
)
@pytest.mark.parametrize("nulls", ["none", "some"])
def test_interleave_columns(nulls, num_cols, num_rows, dtype, dropna):
    if dtype not in ["float32", "float64"] and nulls in ["some"]:
        pytest.skip(msg="nulls not supported in dtype: " + dtype)

    pdf = pd.Series()
    for i in range(num_cols):
        colname = str(i)
        data = np.random.randint(0, 26, num_rows).astype(dtype)
        if nulls == "some":
            idx = np.random.choice(
                num_rows, size=int(num_rows / 2), replace=False
            )
            data[idx] = np.nan
        pdf[colname] = data

    gdf = DataFrame.from_pandas(pdf)

    got = cudf_interleave_columns(gdf)
    expect = cudf_interleave_columns(pdf)
    if {None} == set(expect.index.names):
        expect.rename_axis(
            list(range(0, len(expect.index.names))), inplace=True
        )

    assert_eq(expect, got)
    pass

@pytest.mark.parametrize("num_cols", [1, 2, 10])
@pytest.mark.parametrize("num_rows", [1, 2, 1000])
@pytest.mark.parametrize(
    "dtype",
    [
        "int8",
        "int16",
        "int32",
        "int64",
        "float32",
        "float64",
        "datetime64[ms]",
        "str",
    ],
)
@pytest.mark.parametrize("nulls", ["none", "some"])
def test_tile(nulls, num_cols, num_rows, dtype):
    if dtype not in ["float32", "float64"] and nulls in ["some"]:
        pytest.skip(msg="nulls not supported in dtype: " + dtype)

    pdf = pd.DataFrame()
    for i in range(num_cols):
        colname = str(i)
        data = np.random.randint(0, 26, num_rows).astype(dtype)
        if nulls == "some":
            idx = np.random.choice(
                num_rows, size=int(num_rows / 2), replace=False
            )
            data[idx] = np.nan
        pdf[colname] = data

    gdf = DataFrame.from_pandas(pdf)

    got = cudf_tile(gdf)
    expect = cudf_tile(pdf)
    if {None} == set(expect.index.names):
        expect.rename_axis(
            list(range(0, len(expect.index.names))), inplace=True
        )

    assert_eq(expect, got)
    pass
