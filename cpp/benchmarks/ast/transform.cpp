/*
 * Copyright (c) 2020-2022, NVIDIA CORPORATION.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <benchmarks/common/generate_input.hpp>
#include <benchmarks/fixture/benchmark_fixture.hpp>
#include <benchmarks/synchronization/synchronization.hpp>

#include <cudf/transform.hpp>
#include <cudf/types.hpp>

#include <thrust/iterator/counting_iterator.h>

#include <algorithm>
#include <list>
#include <memory>
#include <vector>

enum class TreeType {
  IMBALANCED_LEFT  // All operator expressions have a left child operator expression and a right
                   // child column reference
};

template <typename key_type, TreeType tree_type, bool reuse_columns, bool Nullable>
class AST : public cudf::benchmark {
};

template <typename key_type, TreeType tree_type, bool reuse_columns, bool Nullable>
static void BM_ast_transform(benchmark::State& state)
{
  auto const table_size{static_cast<cudf::size_type>(state.range(0))};
  auto const tree_levels{static_cast<cudf::size_type>(state.range(1))};

  // Create table data
  auto const n_cols = reuse_columns ? 1 : tree_levels + 1;
  auto const source_table =
    create_sequence_table(cycle_dtypes({cudf::type_to_id<key_type>()}, n_cols),
                          row_count{table_size},
                          Nullable ? 0.5 : -1.0);
  auto table = source_table->view();

  // Create column references
  auto column_refs = std::vector<cudf::ast::column_reference>();
  std::transform(thrust::make_counting_iterator(0),
                 thrust::make_counting_iterator(n_cols),
                 std::back_inserter(column_refs),
                 [](auto const& column_id) {
                   return cudf::ast::column_reference(reuse_columns ? 0 : column_id);
                 });

  // Create expression trees

  // Note that a std::list is required here because of its guarantees against reference invalidation
  // when items are added or removed. References to items in a std::vector are not safe if the
  // vector must re-allocate.
  auto expressions = std::list<cudf::ast::operation>();

  // Construct tree that chains additions like (((a + b) + c) + d)
  auto const op = cudf::ast::ast_operator::ADD;
  if (reuse_columns) {
    expressions.push_back(cudf::ast::operation(op, column_refs.at(0), column_refs.at(0)));
    for (cudf::size_type i = 0; i < tree_levels - 1; i++) {
      expressions.push_back(cudf::ast::operation(op, expressions.back(), column_refs.at(0)));
    }
  } else {
    expressions.push_back(cudf::ast::operation(op, column_refs.at(0), column_refs.at(1)));
    std::transform(std::next(column_refs.cbegin(), 2),
                   column_refs.cend(),
                   std::back_inserter(expressions),
                   [&](auto const& column_ref) {
                     return cudf::ast::operation(op, expressions.back(), column_ref);
                   });
  }

  auto const& expression_tree_root = expressions.back();

  // Execute benchmark
  for (auto _ : state) {
    cuda_event_timer raii(state, true);  // flush_l2_cache = true, stream = 0
    cudf::compute_column(table, expression_tree_root);
  }

  // Use the number of bytes read from global memory
  state.SetBytesProcessed(static_cast<int64_t>(state.iterations()) * state.range(0) *
                          (tree_levels + 1) * sizeof(key_type));
}

static void CustomRanges(benchmark::internal::Benchmark* b)
{
  auto row_counts       = std::vector<cudf::size_type>{100'000, 1'000'000, 10'000'000, 100'000'000};
  auto operation_counts = std::vector<cudf::size_type>{1, 5, 10};
  for (auto const& row_count : row_counts) {
    for (auto const& operation_count : operation_counts) {
      b->Args({row_count, operation_count});
    }
  }
}

#define AST_TRANSFORM_BENCHMARK_DEFINE(name, key_type, tree_type, reuse_columns, nullable) \
  BENCHMARK_TEMPLATE_DEFINE_F(AST, name, key_type, tree_type, reuse_columns, nullable)     \
  (::benchmark::State & st)                                                                \
  {                                                                                        \
    BM_ast_transform<key_type, tree_type, reuse_columns, nullable>(st);                    \
  }                                                                                        \
  BENCHMARK_REGISTER_F(AST, name)                                                          \
    ->Apply(CustomRanges)                                                                  \
    ->Unit(benchmark::kMillisecond)                                                        \
    ->UseManualTime();

AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_int32_imbalanced_unique, int32_t, TreeType::IMBALANCED_LEFT, false, false);
AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_int32_imbalanced_reuse, int32_t, TreeType::IMBALANCED_LEFT, true, false);
AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_double_imbalanced_unique, double, TreeType::IMBALANCED_LEFT, false, false);

AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_int32_imbalanced_unique_nulls, int32_t, TreeType::IMBALANCED_LEFT, false, true);
AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_int32_imbalanced_reuse_nulls, int32_t, TreeType::IMBALANCED_LEFT, true, true);
AST_TRANSFORM_BENCHMARK_DEFINE(
  ast_double_imbalanced_unique_nulls, double, TreeType::IMBALANCED_LEFT, false, true);
