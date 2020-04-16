from ui import script

import dash_html_components as html
from ui import script

class Simple(script.Script):
    def do_run(self, exe):
        driver_name = self.yaml_desc["driver"]
        record_time = int(self.yaml_desc["record_time"])

        first_record = True
        def init_recording(test_name):
            exe.wait(5)
            exe.clear_record()
            exe.clear_quality()
            exe.request("share_pipeline", client=True, agent=True)
            exe.apply_settings("share_encoding", {})
            exe.append_quality(f"!running: {self.name}")
            exe.append_quality(f"!running: {self.name} / {test_name}")
            exe.wait(1)

        for cmd in self.yaml_desc.get("before", []): exe.execute(cmd)

        exe.reset_encoder()

        for test_name, test_cfg in self.yaml_desc["run"].items():
            if test_cfg.get("_disabled", False):
                exe.log(f"{self.name} / {test_name}: disabled")
                continue

            if not first_record:
                exe.append_quality(f"!running: {self.name} / {test_name}")
            rolling_param  = None
            fixed_params = {}

            for param_name, param_value in test_cfg.items():
                if param_name.startswith("_"):
                    assert rolling_param is None
                    rolling_param = param_name[1:], param_value
                    continue

                fixed_params[param_name] = param_value

            first_test = True
            for rolling_param_value in rolling_param[1].split(", "):
                if first_test:
                    first_test = True

                    first_params = {**fixed_params, **{rolling_param[0]: rolling_param_value}}
                    exe.apply_settings(driver_name, first_params)

                    if first_record:
                        first_record = False

                        # this late initialization is necessary to
                        # ensure that the recording data are 100%
                        # clean: the first encoding config is already
                        # set, so no data from the previous
                        # configuration is recorded
                        init_recording(test_name)

                        exe.apply_settings(driver_name, first_params)
                else:
                    exe.apply_settings(driver_name, {rolling_param[0]: rolling_param_value})

                exe.wait(record_time)

            exe.reset_encoder()

        exe.append_quality(f"!finished: {self.name}")

        dest = (f"{script.RESULTS_PATH}/simple/{self.to_id()}_"
                + datetime.datetime.today().strftime("%Y%m%d-%H%M")
                + ".rec")

        exe.save_record(dest)

        for cmd in self.yaml_desc.get("after", []): exe.execute(cmd)

        exe.log("done!")
