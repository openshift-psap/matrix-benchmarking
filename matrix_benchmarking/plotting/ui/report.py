import pathlib
import logging

from dash import html
from dash import dcc

class _Report():
    def __init__(self, id_name, index):
        self.id_name = id_name
        self.index = index

        self.figure_index = 0

    def _children_element_to_html(self, elt):


        if elt.children is None:
            return [f"<{elt._type.lower()}/>"]

        content = [f"<{elt._type.lower()}>"]
        if isinstance(elt.children, str):
            content += [elt.children]
        else:
            for child in elt.children:
                content += self._element_to_html(child)

        content += [f"</{elt._type.lower()}>"]

        return content

    def _graph_element_to_html(self, graph):
        figure = graph.figure
        if not figure:
            return ["<i>no graph available</i>"]

        dirname = f"report_{self.index:02d}_{self.id_name}_files"
        pathlib.Path(dirname).mkdir(exist_ok=True)
        dest = f"{dirname}/fig_{self.figure_index}"

        self.figure_index += 1

        logging.info(f"Saving {dest} ...")
        figure.write_html(f"{dest}.html")
        figure.write_image(f"{dest}.png")

        return [
            f"<p><a href='{dest}.html' target='_blank' title='Click to access the full-size interactive version.'><img src='{dest}.png'/></a></p>"
        ]

    def _element_to_html(self, elt):
        if isinstance(elt, str):
            return [elt]
        elif hasattr(elt, "children"):
            return self._children_element_to_html(elt)
        elif isinstance(elt, dcc.Graph):
            return self._graph_element_to_html(elt)
        else:
            logging.warning("Unsupported report element:", elt.__class__.__name__)
            pass

    def generate(self, content):
        header = [
            "<p><i>Click on the image to open the interactive full-size view of the plot.<i><br/>",
            "<i>In the interactive view, click in the legend to hide a line, double click to see only this line..<i></p>",
            "<hr>",
        ]
        html = header + self._element_to_html(content)

        html_content = "\n".join(html)

        dest = f"report_{self.index}_{self.id_name}.html"
        print(f"Saving {dest} ...")
        with open(dest, "w") as out_f:
            print(html_content, file=out_f)


def generate(idx, id_name, content):
    _Report(id_name, idx).generate(content)
