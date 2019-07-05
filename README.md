Spice Streaming benchmarking and visualization
==============================================


To run the visualization GUI, you need to install some system dependencies
and some Python packages:

System dependencies
-------------------

> dnf install libpq-devel # Postgres
> dnf install pygobject3 python3-gobject # GI

Python dependencies
-------------------

The Python dependencies are listed in the Pipenv file. Install them
with this command:

> pipenv install

then run the GUI with pipenv:

> pipenv run ./ui/main_window.py

or setup the shell environment:

> pipenv shell
> ./ui/main_window.py
