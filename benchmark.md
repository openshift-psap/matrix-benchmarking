Benchmark script
================

The purpose of the benchmark script is to execute automatically measurement
for streaming in SPICE.
After configuring the configuration file `benchmark.yaml` you should
be able to launch the script and get the results, time and resources
permitting.
If you have sensible information to store you can set also a
`secure.yaml` file with the sensible information. These data will
be merged into the main one launching the script.

The script uses some modules which can be added or changed.

The purpose of the script should to do the measurements, not setting
up all the environment, for instance

 * VM must be setup;
 * you should configure ssh not having to ask password;
 * screen savers or screen locks should be disabled;
 * if you need machine logged you have to do login or setup
   autologin.

measurement module
------------------
Each measurement has its own module. The file
`measurement/__init__.py` is the base and should be well documented in
order to create new measurement. Inside `measurement` directory there
are the specific measurement with some real one and some test/example
one (like `test.py`).

The configuration file allows to define which measurement to activate
and the configuration of each one.

Each specific module define the steps required:

 * setup
 * start
 * stop
 * collect

(see `measurement/__init__.py` for description).

The output of each measurement (that should be set in the `collect`
phase) should be stored in tables, created using the `Experiment`
module. An `experiment` object is stored in the base `Measurement` for
convenience.

experiment module
-----------------
This modules contains the `Experiment` object which represent the
experiment.


### Experiment object
A module should create tables to save output with the `create_table`
method.

You can add any possible attachment (metadata for the experiment like
output of command) with `add_attachment`.

### Table object
This simple object stores tables for the experiment. They do not
entirely represent physical tables but they will be converted to
physical one by the when the experiment is saved (`save` method or
`Experiment`).

To create a table simply pass the field names to `create_table` (see
`Experiment`).

To populate a table simply call the method `add` passing the field
values.

**NOTE**
Many todos, one missing part is utilities to manage remote machine and
their configuration.

SSH configuration
-----------------
Current code managng remote machines is using heavily `ssh` command.
You should configure `ssh` to not require password.
Also ssh should be configured to work pretty fast.
There are some caveats that could make `ssh` slower:

 * authentication. If the authentication requires some external
   communication this could take some time. Check with `ssh -v`.
 * connection. If connection is slow try to use `ControlMaster`,
   `ControlPath` and `ControlPersist` options. They allow to reuse
   connections.


upload-data.py script
=====================

This is a small utility to import benchmark into a shared database.
Currently the only database supported is Postgresql. Configure the
same file for the `benchmark` script (you have to fill also the
`databases/remote` part). One done you can launch the script to
import the local database into the remote one.

Experiments imported will be marked as imported so they won't be
imported again.
