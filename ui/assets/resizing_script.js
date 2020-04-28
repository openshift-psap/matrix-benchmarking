if (!window.dash_clientside) {
    window.dash_clientside = {};
}

window.dash_clientside.clientside = {
    resize: function(value) {
        setTimeout(function() {
            window.dispatchEvent(new Event("resize"));
        }, 500);
        return null;
    },

    resize_graph: function(input_graph_style,) {
        window.dispatchEvent(new Event("resize"));
        setTimeout(function() {
            window.dispatchEvent(new Event("resize"));
        }, 500);
        return null;
    },
};
