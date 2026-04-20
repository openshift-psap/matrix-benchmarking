import pathlib
import logging

from dash import html
from dash import dcc

class _Report():
    def __init__(self, id_name, index):
        self.id_name = id_name
        self.index = index

        self.figure_index = 0
        self.tabs_css_added = False
        self.tabs_container_id = 0

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
            msg = f"Failed to save graph #{self.index} {self.id_name} '{figure.layout.title.text}':"
            logging.exception(f"Failed to save graph #{self.index} {self.id_name}: {e}")

            return [
                f"<p>{msg}: {e}</p>"
            ]

        return [
            f"<p><a href='{dest}.html' target='_blank' title='Click to access the full-size interactive version.'><img src='{dest}.png'/></a></p>"
         ]

    def _tabs_element_to_html(self, tabs):
        """Convert dcc.Tabs to HTML with proper tab navigation"""
        content = []

        # Add CSS and JavaScript the first time tabs are used
        if not self.tabs_css_added:
            content.append("""
<style>
.tabs-container {
    margin: 20px 0;
    border: 1px solid #ddd;
    border-radius: 8px;
    background-color: #f9f9f9;
}

.tab-headers {
    display: flex;
    background-color: #f1f1f1;
    border-bottom: 1px solid #ddd;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}

.tab-header {
    background-color: #e1e1e1;
    color: #333;
    padding: 15px 20px;
    cursor: pointer;
    border: none;
    border-right: 1px solid #ddd;
    font-family: Arial, sans-serif;
    font-size: 16px;
    font-weight: bold;
    transition: background-color 0.3s;
}

.tab-header:hover {
    background-color: #d1d1d1;
}

.tab-header.active {
    background-color: #4CAF50;
    color: white;
}

.tab-header:first-child {
    border-top-left-radius: 8px;
}

.tab-header:last-child {
    border-right: none;
    border-top-right-radius: 8px;
}

.tab-content {
    padding: 20px;
    background-color: white;
    display: none;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
}

.tab-content.active {
    display: block;
}
</style>

<script>
function showTab(containerId, tabId, buttonElement) {
    // Get the specific container
    var container = document.getElementById(containerId);

    // Hide all tab contents within this container
    var contents = container.querySelectorAll('.tab-content');
    for (var i = 0; i < contents.length; i++) {
        contents[i].classList.remove('active');
    }

    // Remove active class from all headers within this container
    var headers = container.querySelectorAll('.tab-header');
    for (var i = 0; i < headers.length; i++) {
        headers[i].classList.remove('active');
    }

    // Show selected tab content and mark header as active
    document.getElementById(tabId).classList.add('active');
    buttonElement.classList.add('active');
}
</script>
""")
            self.tabs_css_added = True

        if not tabs.children:
            return ["<div class='tabs-container'><p>No tabs available</p></div>"]

        # Generate unique container and tab IDs
        container_id = f"tabs-container-{self.index}-{self.tabs_container_id}"
        self.tabs_container_id += 1
        tab_count = len(tabs.children)
        tab_ids = [f"tab-{self.index}-{self.tabs_container_id-1}-{i}" for i in range(tab_count)]

        content.append(f"<div id='{container_id}' class='tabs-container'>")

        # Create tab headers
        content.append("<div class='tab-headers'>")
        for i, tab in enumerate(tabs.children):
            label = getattr(tab, 'label', f'Tab {i+1}')
            active_class = ' active' if i == 0 else ''
            content.append(f"<button class='tab-header{active_class}' onclick=\"showTab('{container_id}', '{tab_ids[i]}', this)\">{label}</button>")
        content.append("</div>")

        # Create tab contents
        for i, tab in enumerate(tabs.children):
            active_class = ' active' if i == 0 else ''
            content.append(f"<div id='{tab_ids[i]}' class='tab-content{active_class}'>")
            if tab.children:
                if isinstance(tab.children, list):
                    for child in tab.children:
                        content += self._element_to_html(child)
                else:
                    content += self._element_to_html(tab.children)
            content.append("</div>")

        content.append("</div>")
        return content

    def _tab_element_to_html(self, tab):
        """Convert individual dcc.Tab to HTML - used when tab is standalone"""
        content = []

        # Add tab label as heading if it exists
        if hasattr(tab, 'label') and tab.label:
            content.append(f"<h3 class='standalone-tab-label'>{tab.label}</h3>")

        # Add tab content
        if tab.children:
            content.append("<div class='standalone-tab-content'>")
            if isinstance(tab.children, list):
                for child in tab.children:
                    content += self._element_to_html(child)
            else:
                content += self._element_to_html(tab.children)
            content.append("</div>")

        return content

    def _element_to_html(self, elt):
        if elt is None:
            return ["None"]
        elif isinstance(elt, str):
            return [elt]
        elif any([isinstance(elt, t) for t in (str, float, int)]):
            return [str(elt)]
        elif isinstance(elt, dcc.Tabs):
            return self._tabs_element_to_html(elt)
        elif isinstance(elt, dcc.Tab):
            return self._tab_element_to_html(elt)
        elif hasattr(elt, "children"):
            return self._children_element_to_html(elt)
        elif isinstance(elt, dcc.Graph):
            return self._graph_element_to_html(elt)
        elif to_html := getattr(elt, "to_html", None):
            return [to_html()]
        else:
            logging.warning("Unsupported report element: %s", elt.__class__.__name__)
            return [str(elt)]

    def generate(self, content, report_index_f, include_header):
        # HTML document structure with proper headers for emoji support
        html_doc_start = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"    <title>{self.id_name.replace('_', ' ').title()}</title>",
            "</head>",
            "<body>",
        ]

        html_doc_end = [
            "</body>",
            "</html>"
        ]

        html = []
        html += html_doc_start

        if include_header:
            header = [
                "<p><i>Click on the image to open the interactive full-size view of the plot.</i><br/>",
                "<i>In the interactive view, click in the legend to hide a line, double click to see only this line.</i></p>",
                "<p><a href='reports_index.html'>Back to the reports index.</a></p>"
                "<hr>",
            ]
            html += header

        html += self._element_to_html(content)
        html += html_doc_end

        html_content = "\n".join(html)

        if self.index is not None:
            dest = f"report_{self.index:02d}_{self.id_name}.html"
        else:
            dest = self.id_name

        logging.info(f"Saving {dest} ...")
        with open(dest, "w", encoding='utf-8') as out_f:
            print(html_content, file=out_f)

        if report_index_f is not None:
            print(f"<li><a href='{dest}'> Report {self.index:02d}: {self.id_name.replace('_', ' ')}</a>",
                  file=report_index_f)

def generate(idx, id_name, content, report_index_f, include_header=True):
    _Report(id_name, idx).generate(content, report_index_f, include_header)
