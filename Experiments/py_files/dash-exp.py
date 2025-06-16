from pydoc import classname
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    meta_tags=[{
        'name': 'viewport',
        'content': 'width=device-width, initial-scale=1.0'
    }]
)

app.layout = dbc.Container(
    [
        dbc.Alert("Hello Bootstrap!", color="success", className="mt-5"),
        dbc.Button("Click Me", color="primary", className="mt-3"),

    ],
    fluid=True,
    className="p-5",
)

if __name__ == "__main__":
    app.run(debug=True)