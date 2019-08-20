# Copyright (c) 2019, NVIDIA CORPORATION.

# cython: profile=False
# distutils: language = c++
# cython: embedsignature = True
# cython: language_level = 3

from cudf.bindings.cudf_cpp cimport *
from cudf.bindings.cudf_cpp import *
from cudf.bindings.utils cimport *
from cudf.bindings.utils import *

from cudf.bindings.copying cimport cols_view_from_cols, free_table
from cudf.bindings.copying import clone_columns_with_size
from cudf.bindings.stream_compaction cimport *


def apply_drop_duplicates(in_index, in_cols, subset=None, keep='first'):
    """
    get unique entries of subset columns from input columns

    in_index: index column of input dataframe
    in_cols: list of input columns to filter
    subset:  list of columns to consider for identifying duplicate rows
    keep: keep 'first' entry or 'last' if duplicate rows are found

    out_cols: columns containing only unique rows
    out_index: index of unique rows as column
    """
    cdef col_count=len(in_cols)
    cdef row_count=len(in_index[0])
    if col_count == 0 or row_count == 0:
        return clone_columns_with_size(in_cols, row_count), in_index[0].copy()

    cdef gdf_column** c_in_cols = cols_view_from_cols(in_cols+in_index)
    cdef cudf_table* c_in_table = new cudf_table(c_in_cols, col_count+1)

    cdef duplicate_keep_option keep_first
    if keep == 'first':
        keep_first = duplicate_keep_option.KEEP_FIRST
    elif keep == 'last':
        keep_first = duplicate_keep_option.KEEP_LAST
    elif keep is False:
        keep_first = duplicate_keep_option.KEEP_NONE
    else:
        raise ValueError('keep must be either "first", "last" or False')

    # check subset == in_cols and subset=None cases
    cdef gdf_column** key_cols
    cdef cudf_table* key_table
    if subset == in_cols or subset is None:
        key_cols = cols_view_from_cols(in_cols)
        key_table = new cudf_table(key_cols, len(in_cols))
    else:
        key_cols = cols_view_from_cols(subset)
        key_table = new cudf_table(key_cols, len(subset))

    cdef cudf_table c_out_table
    with nogil:
        c_out_table = drop_duplicates(c_in_table[0], key_table[0], keep_first)

    free_table(key_table, key_cols)
    free_table(c_in_table, c_in_cols)

    # convert table to columns, index
    out_cols = columns_from_table(&c_out_table)

    return (out_cols[:-1], out_cols[-1])


def nunique(in_col):
    """
    get number of unique elements in the input column

    in_col: input column to check for unique element count

    out_count: number of unique elements in the input column
    """
    in_col_null = in_col
    # convert nans_to_nulls
    if (in_col.dtype in [np.float16, np.float32, np.float64]):
        in_col_null = in_col.set_mask(mask_from_devary(in_col))
    check_gdf_compatibility(in_col_null)
    cdef gdf_column* c_in_col = column_view_from_column(in_col_null)
    cdef int count = 0
    with nogil:
        count = unique_count(c_in_col[0])
    # if null and nan both are present, increment count by 1
    if in_col.null_count>0 and in_col_null.null_count > in_col.null_count:
        count = count + 1
    return count


def apply_apply_boolean_mask(cols, mask):
    """
    Filter the rows of a list of columns using a boolean mask

    Parameters
    ----------
    cols : List of Columns
    mask : Boolean mask (Column)

    Returns
    -------
    List of Columns
    """
    cdef cudf_table  c_out_table
    cdef cudf_table* c_in_table = table_from_columns(cols)
    cdef gdf_column* c_mask_col = column_view_from_column(mask)

    with nogil:
        c_out_table = apply_boolean_mask(c_in_table[0], c_mask_col[0])

    free_table(c_in_table)
    free_column(c_mask_col)

    return columns_from_table(&c_out_table)


def apply_drop_nulls(cols, how="any", subset=None, thresh=None):
    """
    Drops null rows from cols.

    Parameters
    ----------
    cols : List of Columns
    how  : "any" or "all". If thresh is None, drops rows of cols that have any
           nulls or all nulls (respectively) in subset (default: "any")
    subset : List of Columns. If set, then these columns are checked for nulls
             rather than all of cols (optional)
    thresh : Minimum number of non-nulls required to keep a row (optional)

    Returns
    -------
    List of Columns
    """
    from cudf.dataframe.categorical import CategoricalColumn

    cdef cudf_table c_out_table
    cdef cudf_table* c_in_table = table_from_columns(cols)

    # if subset is None, we use cols as keys
    # if subset is empty, we pass an empty keys table, which will cause
    # cudf::drop_nulls() to return a copy of the input table
    cdef cudf_table* c_keys_table = (table_from_columns(cols) if subset is None
                                     else table_from_columns(subset))

    # default: "any" means threshold should be number of key columns
    cdef gdf_size_type c_keep_threshold = (len(cols) if subset is None
                                           else len(subset))

    # Use `thresh` if specified, otherwise set threshold based on `how`
    if thresh is not None:
        c_keep_threshold = thresh
    elif how == "all":
        c_keep_threshold = 1

    with nogil:
        c_out_table = drop_nulls(c_in_table[0], c_keys_table[0],
                                 c_keep_threshold)

    free_table(c_in_table)
    free_table(c_keys_table)

    result_cols = columns_from_table(&c_out_table)

    for i, inp_col in enumerate(cols):
        if isinstance(inp_col, CategoricalColumn):
            result_cols[i] = CategoricalColumn(
                data=result_cols[i].data,
                mask=result_cols[i].mask,
                categories=inp_col.cat().categories,
                ordered=inp_col.cat().ordered)

    return result_cols
