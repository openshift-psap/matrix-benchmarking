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
        props = " ".join([f"{k}='{getattr(elt, k)}'" for k in elt.available_properties if k not in ("children", "style") and hasattr(elt, k)])

        if hasattr(elt, "style"):
            if not isinstance(elt.style, dict):
                logging.warning("The 'style' attribute should be a dict ...")
                props += f" style='{elt.style}'"
            else:
                props += " style='" + " ".join([f"{k}:{v};" for k,v in elt.style.items()]) + "'"

        content = [f"<{elt._type.lower()}{' ' if props else ''}{props}{'/' if not elt.children else ''}>"]

        if elt.children is None:
            return content

        if isinstance(elt.children, str):
            content += [elt.children]
        elif hasattr(elt.children, "_type"):
            content += self._children_element_to_html(elt.children)
        else:
            try:
                it = iter(elt.children)
            except TypeError:
                it = None # not iterable

            if it:
                for child in it:
                    content += self._element_to_html(child)
            else:
                content += [str(elt.children)]

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
        dest_html = f"{dest}.html"
        dest_png = f"{dest}.png"

        from .web import IMAGE_WIDTH, IMAGE_HEIGHT
        try:
            figure.write_html(dest_html)
            figure.write_image(dest_png, width=IMAGE_WIDTH, height=IMAGE_HEIGHT)
        except Exception as e:
            msg = f"Failed to save graph #{self.index} {self.id_name}:"
            logging.error(f"Failed to save graph #{self.index} {self.id_name}: {e}")
            return [
                f"<p>{msg}: {e}</p>"
            ]

        return [
            f"<p><a href='{dest}.html' target='_blank' title='Click to access the full-size interactive version.'><img src='{dest}.png'/></a></p>"
         ]

    def _element_to_html(self, elt):
        if elt is None:
            return ["None"]
        elif isinstance(elt, str):
            return [elt]
        elif hasattr(elt, "children"):
            return self._children_element_to_html(elt)
        elif isinstance(elt, dcc.Graph):
            return self._graph_element_to_html(elt)
        else:
            logging.warning("Unsupported report element: %s", elt.__class__.__name__)
            return [str(elt)]

    def generate(self, content, report_index_f):
        header = [
            "<p><i>Click on the image to open the interactive full-size view of the plot.</i><br/>",
            "<i>In the interactive view, click in the legend to hide a line, double click to see only this line.</i></p>",
            "<p><a href='reports_index.html'>Back to the reports index.</a></p>"
            "<hr>",
        ]
        html = header + self._element_to_html(content)

        html_content = "\n".join(html)

        dest = f"report_{self.index:02d}_{self.id_name}.html"
        print(f"Saving {dest} ...")
        with open(dest, "w") as out_f:
            print(html_content, file=out_f)

        print(f"<li><a href='{dest}'> Report {self.index:02d}: {self.id_name.replace('_', ' ')}</a>",
              file=report_index_f)

def generate(idx, id_name, content, report_index_f):
    _Report(id_name, idx).generate(content, report_index_f)
