import types, os, itertools

from ui.matrix_view import Matrix
from ui import script
import measurement.perf_viewer

from ui.table_stats import TableStats

from .report import Report
from .plot_model import PlotModel, ModelGuestCPU
from .fps_table import FPSTable
from .plot_model import PlotModel
from .encoding_stack import EncodingStack
from .old_encoding_stack import OldEncodingStack
from .regression import Regression
from .distrib_plot import DistribPlot
from .heatmap import HeatmapPlot

FileEntry = types.SimpleNamespace
Params = types.SimpleNamespace

PROPERTY_RENAME = {
    # gst.nvenc

    "gop-size": "keyframe-period",
    "rc-mode": "rate-control",

    # native nvidia plugin
    "ratecontrol": "rate-control",
    "max-bitrate": "bitrate",
    "gop": "keyframe-period",
    "codec": "driver",
}

VALUE_TRANSLATE = {
    "gop-size": {"30": "128", "9000": "512", "-1": "512"},
    "gop": {"30": "128", "9000": "512", "-1": "512"},
    #"keyframe-period": {"30": "128", "9000": "512"},
    #"framerate": {"200": "60"},
    "driver": {"gst.vp8.vaapivp8enc": "___"},
    "codec": {"gst.h264.nvh264enc": "___",
               "gst.vp8.vaapivp8enc": "___",
               "gst.h264.vaapih264enc": "___",
               "nv.plug.h264": "___",

    }
}

def rewrite_properties(params_dict):
    new_params_dict = {}
    for k, v in params_dict.items():
        v = VALUE_TRANSLATE.get(k, {}).get(v, v)
        k = PROPERTY_RENAME.get(k, k)

        new_params_dict[k] = v
    return new_params_dict

key_order = None

def parse_data(filename, reloading=False):
    if not os.path.exists(filename): return
    directory = filename.rpartition(os.sep)[0]

    expe = filename[len(script.RESULTS_PATH)+1:].partition("/")[0]
    expe_name = expe.replace("_", "-")

    with open(filename) as record_f:
        lines = record_f.readlines()

    for _line in lines:
        line = _line[:-1].partition("#")[0].strip()
        if not line: continue

        entry = FileEntry()
        entry.params = Params()

        # codec=gst.vp8.vaapivp8enc_record-time=30s_resolution=1920x1080_webpage=cubemap | 1920x1080/cubemap | bitrate=1000_rate-control=cbr_keyframe-period=25_framerate=35.rec

        script_key, file_path, file_key = line.split(" | ")
        entry_key = "_".join([f"experiment={expe_name}", script_key, file_key])

        params_dict = {}
        for kv in entry_key.split("_"):
            k, v = kv.split("=")
            params_dict[k] = v

        if not reloading:
            param_dict = rewrite_properties(params_dict)

        entry.params.__dict__.update(params_dict)

        global key_order
        if key_order is None:
            key_order = tuple(entry.params.__dict__)

        entry.key = "_".join([f"{k}={entry.params.__dict__.get(k)}" for k in key_order])

        entry.filename = os.sep.join([directory, file_path, file_key+".rec"])
        entry.linkname = os.sep.join(["results", expe, file_path, file_key+".rec"])

        if not os.path.exists(entry.filename):
            print("missing:", entry.filename)
            continue

        try:
            dup_entry = Matrix.entry_map[entry.key]
            if not reloading and dup_entry.filename != entry.filename:
                print(f"WARNING: duplicated key: {entry.key} ({entry.filename})")
                print(f"\t 1: {dup_entry.filename}")
                print(f"\t 2: {entry.filename}")
                continue
        except KeyError: pass # not duplicated

        with open(entry.filename) as rec_f:
            parser = measurement.perf_viewer.parse_rec_file(rec_f)
            _, feedback_rows = next(parser)

            entry.tables = {}

            while True:
                _, table_def = next(parser)
                if not table_def: break

                _, table_rows= next(parser)
                _, feedback_rows = next(parser)

                table_name = table_def.partition("|")[0][1:]

                entry.tables[table_def] = table_name, table_rows

        if table_def is not None: # didn't break because not enough entries
            continue

        for param, value in entry.params.__dict__.items():
            try: value = int(value)
            except ValueError: pass # not a number, keep it as a string
            Matrix.properties[param].add(value)

        Matrix.entry_map[entry.key] = entry

        entry.stats = {}
        for table_stat in TableStats.all_stats:

            if isinstance(table_stat, TableStats):
                register = False
                for table_def, (table_name, table_rows) in entry.tables.items():
                    if (table_stat.table != table_name and not
                        (table_stat.table.startswith("?.") and table_name.endswith(table_stat.table[1:]))):
                        continue
                    entry.stats[table_stat.name] = table_stat.process(table_def, table_rows)
                    register = True
            else: register = True

            if register:
                Matrix.properties["stats"].add(table_stat.name)

def all_records(params, param_lists):
    for param_values in sorted(itertools.product(*param_lists)):
        params.update(dict(param_values))
        key = "_".join([f"{k}={params[k]}" for k in key_order])
        try:
            yield Matrix.entry_map[key]
        except KeyError:
            continue # missing experiment

def get_record(variables):
    key = "_".join([f"{k}={variables[k]}" for k in key_order])

    try: return Matrix.entry_map[key]
    except KeyError: return None

def register():
    from . import plot_model
    plot_model.Regression = Regression

    for what in "framerate", "resolution":
        Report.CPU(what)
        Report.Decode(what)
        for sys in "guest", "client":
            for engine in "Render", "Video":
                Report.GPU(what, sys=sys, engine=engine)

    Report.GuestCPU()

    PlotModel("Guest CPU Usage", "guest_cpu", PlotModel.estimate_guest_cpu_value)
    PlotModel("Guest GPU Render Usage", "guest_gpu_render", PlotModel.estimate_guest_gpu_render_value)
    ModelGuestCPU()
    FPSTable()
    EncodingStack()
    OldEncodingStack()

    for who in "client", "guest":
        Who = who.capitalize()
        for what_param, what_x in (
                ("framerate", f"{Who} Framerate"),
                ("resolution", "param:resolution:res_in_mpix"),
                ("bitrate", "param:bitrate:bitrate_in_mbps"),
                ("keyframe-period", "param:keyframe-period:keyframe_period")):
            for y_name in "CPU", "GPU Video", "GPU Render":
                y_id = y_name.lower().replace(" ", "_")
                Regression(f"{what_param}_vs_{who}_{y_id}", what_param, f"{Who} {y_name} vs {what_param.title()}", what_x, f"{Who} {y_name}")

    for what_param, what_x in ("framerate", f"Client Framerate"), ("resolution", "param:resolution:res_in_mpix"):
        Regression(f"{what_param}_vs_decode_time", what_param, f"Client Decode Time vs {what_param.title()}",
                   what_x, f"Client Decode time/s")

        Regression(f"{what_param}_vs_time_in_queue", what_param, f"Time in Client Queue vs {what_param.title()}",
                   what_x, f"Client time in queue (per second)")

        if what_x == "Client Framerate": what_x = "param:framerate:FPS"
        Regression(f"{what_param}_vs_bandwidth", what_param, f"Frame Bandwidth vs {what_param.title()}",
                   what_x, f"Frame Size (avg)")

    Regression(f"resolution_vs_decode_time", "resolution", f"Guest Capture Duration (avg) vs Resolution",
               "param:resolution:res_in_mpix", "Guest Capture Duration (avg)")

    Regression(f"bandwidth_vs_bitrate", "bitrate", f"Bandwidth vs Bitrate",
               "param:bitrate:bitrate_in_mbps", "Frame Bandwidth (per sec)")

    DistribPlot("Frame capture time", 'guest.guest', 'guest.capture_duration', "ms", divisor=1/1000)
    DistribPlot("Frame sizes", 'guest.guest', 'guest.frame_size', "KB", divisor=1000)

    HeatmapPlot("Frame Size/Decoding", 'client.client', "Frame Size vs Decode duration",
                ("client.frame_size", "Frame size (in KB)", 0.001),
                ("client.decode_duration", "Decode duration (in ms)", 1000))

    TableStats.PerSecond("frame_size_per_sec", "Frame Bandwidth (per sec)", "server.host",
                          ("host.msg_ts", "host.frame_size"), ".2f", "MB/s", divisor=1000*1000)

    TableStats.Average("frame_size", "Frame Size (avg)", "server.host",
                       "host.frame_size", ".2f", "KB", divisor=1000)

    TableStats.KeyFramesCount("keyframe_count", "Keyframe count", "guest.guest",
                              "guest.key_frame", ".0f", "#", keyframes=True)
    TableStats.KeyFramesCount("p_frame_count", "P-frame count", "guest.guest",
                              "guest.key_frame", ".0f", "#", keyframes=False)

    TableStats.KeyFramesCount("all_frame_count", "All-frame count", "guest.guest",
                              "guest.key_frame", ".0f", "#", keyframes=None)

    TableStats.Average("client_time_in_queue_avg", "Client time in queue (avg)",
                       "client.frames_time_to_drop", "frames_time_to_drop.in_queue_time", ".0f", "ms",
                       divisor=1000)

    for what in "sleep", "encode", "send", "pull":
        frames = (True, "I-frames"), (False, "P-frames"), (None, "")
        for kfr, kfr_txt in frames:
            TableStats.Average(f"guest_{what}_duration_{kfr_txt}", f"Guest {what.capitalize()} Duration (avg){' ' if kfr_txt else ''}{kfr_txt}",
                               "guest.guest", f"guest.{what}_duration", ".0f", "ms", keyframes=kfr, divisor=1/1000)

    for what in "capture", "push":
        TableStats.Average(f"guest_capt_{what}_duration", f"Guest {what.capitalize()} Duration (avg)",
                           "guest.guest_capt", f"guest_capt.{what}_duration", ".0f", "ms", divisor=1/1000)


    TableStats.PerSecond("client_time_in_queue_persec", "Client time in queue (per second)", "client.frames_time_to_drop",
                         ("frames_time_to_drop.msg_ts", "frames_time_to_drop.in_queue_time"), ".0f", "ms/sec", divisor=1000)

    for name in ("server", "client", "guest"):
        TableStats.Average(f"{name}_gpu_video", f"{name.capitalize()} GPU Video",
                           f"{name}.gpu", "gpu.video", ".0f", "%")
        TableStats.Average(f"{name}_gpu_render", f"{name.capitalize()} GPU Render",
                           f"{name}.gpu", "gpu.render", ".0f",  "%")

        TableStats.Average(f"{name}_cpu", f"{name.capitalize()} CPU", f"{name}.{name}-pid",
                           f"{name}-pid.cpu_user", ".0f", "%")

    TableStats.Average(f"client_queue", f"Client Queue", "client.client", "client.queue", ".2f", "")

    for agent_name, tbl_name in (("client", "client"), ("guest", "guest"), ("server", "host")):
        TableStats.AvgTimeDelta(f"{agent_name}_frame_delta", f"{agent_name.capitalize()} Frames Δ",
                                f"{agent_name}.{tbl_name}", f"{tbl_name}.msg_ts", ".2f", "ms")
        TableStats.ActualFramerate(f"{agent_name}_framerate", f"{agent_name.capitalize()} Framerate",
                                   f"{agent_name}.{tbl_name}", f"{tbl_name}.msg_ts", ".0f", "FPS")

        TableStats.ActualFramerate(f"{agent_name}_framerate_time", f"{agent_name.capitalize()} Framerate Time",
                                   f"{agent_name}.{tbl_name}", f"{tbl_name}.msg_ts", ".0f", "ms", invert=True, divisor=1/1000)

        #TableStats.AgentActualFramerate(f"{agent_name}_framerate_agent", f"{agent_name.capitalize()} Agent Framerate",
        #                                f"{agent_name}.{tbl_name}", f"{tbl_name}.framerate_actual", ".0f", "fps")

    TableStats.ActualFramerate(f"guest_capture_framerate", f"Guest Capture Framerate",
                               f"guest.capture", f"capture.msg_ts", ".0f", "FPS")

    TableStats.PerSecond("client_decode_per_s", "Client Decode time/s", "client.client",
                          ("client.msg_ts", "client.decode_duration"), ".0f", "s/s", divisor=1000*1000)

    TableStats.PerFrame("client_decode_per_f", "Client Decode time/frame", "client.client",
                        ("client.msg_ts", "client.decode_duration"), ".0f", "s/frame", divisor=1000*1000)

    TableStats.Average("client_decode", "Client Decode Duration", "client.client",
                       "client.decode_duration", ".0f", "s")

    TableStats.StartStopDiff(f"guest_syst_mem", f"Guest Free Memory", "guest.mem",
                             "mem.free", ".0f", "B", divisor=1000*1000)
    TableStats.Average("guest_syst_mem_avg", "Guest Free Memory (avg)", "guest.mem",
                       "mem.free", ".0f", "MB", divisor=1000)

    TableStats.StartStopDiff(f"frames_dropped", f"Client Frames Dropped", "client.frames_dropped",
                             "frames_dropped.count", "d", "frames")
