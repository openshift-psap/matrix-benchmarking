import copy

from dash import html
from dash import dcc

from common import Matrix
import matrix_view.table_stats

def set_vars(settings, ordered_vars, params, param_lists, variables, cfg):
    _params = dict(params)
    _variables = copy.deepcopy(variables)
    _ordered_vars = list(ordered_vars)
    for k, v in settings.items():
        _params[k] = v
        _variables.pop(k, True)
        if k in _ordered_vars:
            _ordered_vars.remove(k)

    _param_lists = [[(key, v) for v in variables[key]] for key in _ordered_vars]

    return _ordered_vars, _params, _param_lists, _variables, cfg

class OverviewReport():
    def __init__(self):
        self.name = "A test report"
        self.id_name = self.name.lower().replace(" ", "_")
        self.no_graph = True

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_plot(self, *args):
        common_settings = dict(
            #threshold="0.1",
            expe="dgx-benchmark",
            flavor="20211209",
            #execution_mode="fast",
        )

        header = []

        #header += [html.H1("DGX A100 validation benchmark results")]

        exec_time = matrix_view.table_stats.TableStats.stats_by_name['Execution Time']
        multi_gpu_time_to_threshold = matrix_view.table_stats.TableStats.stats_by_name['Multi-GPU time to threshold']
        gpu_isolation_time_to_threshold = matrix_view.table_stats.TableStats.stats_by_name['GPU Isolation time to threshold']

        mig7g_40gb_time_to_threshold = matrix_view.table_stats.TableStats.stats_by_name['MIG 7g.40gb time to threshold']
        # ---

        settings = dict(common_settings) | dict(
            pod_count=1,
            gpu_type="full",
            mig_strategy="none",
        )

        graph = multi_gpu_time_to_threshold.do_plot(*set_vars(settings, *args))[0]

        header += [html.H2("Multi-GPU benchmarking: time to threshold")]
        header += [dcc.Graph(figure=graph)]

        # ---

        settings = dict(common_settings) | dict(
            gpu_type="full",
            gpu_count=1,
            mig_strategy="none",
        )

        graph = gpu_isolation_time_to_threshold.do_plot(*set_vars(settings, *args))[0]

        header += [html.H2(["GPU Isolation benchmarking: time to threshold"])]
        header += [html.P(f"{settings}")]
        header += [dcc.Graph(figure=graph)]

        # ---

        settings = dict(common_settings) | dict(
            gpu_type="7g.40gb",
            pod_count=1,
            mig_strategy="mixed",
        )

        graph = mig7g_40gb_time_to_threshold.do_plot(*set_vars(settings, *args))[0]

        header += [html.H2(["Parallel MIG benchmarking: time to threshold"])]
        header += [html.P(f"{settings}")]
        header += [dcc.Graph(figure=graph)]

        # ---

        settings = dict(common_settings) | dict(
            gpu_type="7g.40gb",
            mig_strategy="single",
        )

        graph = exec_time.do_plot(*set_vars(settings, *args))[0]

        header += [html.H2(["Parallel MIG benchmarking, ", html.B("single mode"),": execution time"])]
        header += [html.P(f"{settings}")]
        header += [dcc.Graph(figure=graph)]

        # ---


        settings = dict(common_settings) | dict(
            gpu_type="2g.10gb,3g.20gb",
            mig_strategy="mixed",
        )

        graph = exec_time.do_plot(*set_vars(settings, *args))[0]

        header += [html.H2(["Parallel MIG benchmarking, ", html.B("multiple MIG types"),": execution time"])]
        header += [html.P(f"{settings}")]
        header += [dcc.Graph(figure=graph)]


        return None, header

class PrometheusMultiGPUReport():
    def __init__(self, metric):
        self.metric = metric
        self.name = f"Prom report: {self.metric}"
        self.id_name = self.name.lower().replace(" ", "_")
        self.no_graph = True

        matrix_view.table_stats.TableStats._register_stat(self)
        Matrix.settings["stats"].add(self.name)

    def do_plot(self, *args):
        common_settings = dict(
            threshold="0.1",
            expe="dgx-quick",
            flavor="20211209",
            execution_mode="fast",
            mig_strategy="mixed",
            pod_count=1,
            gpu_type="full",
        )
        prom_overview = matrix_view.table_stats.TableStats.stats_by_name['Prom: '+self.metric]

        header = [html.H1("Multi-GPU Prometheus Metrics: " + self.metric)]

        # ---
        for gpu_count in args[3]["gpu_count"]:

            settings = dict(common_settings) | dict(
                gpu_count=gpu_count,
            )
            prom_overview_graph = prom_overview.do_plot(*set_vars(settings, *args))[0]

            header += [html.H2([f"{gpu_count} GPU"+("s" if int(gpu_count) > 1 else "")])]
            header += [html.P(f"{settings}")]
            header += [dcc.Graph(figure=prom_overview_graph)]

        return None, header
