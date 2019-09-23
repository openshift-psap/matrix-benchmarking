if (!window.dash_clientside) {
    window.dash_clientside = {};
}
window.dash_clientside.clientside = {
    resize: function(value) {
        console.log("resizing...!"+value); // for testing
        setTimeout(function() {
            window.dispatchEvent(new Event("resize"));
            console.log("fired resize");
        }, 500);
        return null;
    },

    resize_graph: function(input_graph_style,) {
        window.dispatchEvent(new Event("resize"));

        return null;
    },
};
