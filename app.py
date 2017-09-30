import dash
import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Input, Output, State, Event

import dash_table_experiments

import plotly.graph_objs as go

import argparse
import json
import pandas as pd
from sklearn.decomposition import PCA

from ingest_data import parse_input
from transform_data import pca_transform

# Parse command-line
parser = argparse.ArgumentParser(description='App for visualising high-dimensional data')
parser.add_argument('infile', help='CSV file of data to visualise')
parser.add_argument('--separator', default=',', help='separator character in tabular input')
parser.add_argument('--num-pcs', type=int, default='10', help='number of principal components to present')
parser.add_argument('--field-table', dest='show_fieldtable', action='store_true')
# max_PCs
args = parser.parse_args()

# read and parse data
data, sample_info, field_info = parse_input(args.infile, separator=args.separator)
fields = list(data.columns)
assert list(field_info.index) == fields

field_info_table = field_info
field_info_table['Field'] = field_info_table.index

app = dash.Dash()
#app.css.config.serve_locally = True
app.scripts.config.serve_locally = True
app.css.append_css({'external_url': 'https://codepen.io/chriddyp/pen/bWLwgP.css'})

if args.show_fieldtable:
    # Create the fieldinfo table for selecting fields
    fieldinfo_elements = [
        html.Label('Include fields'),
        dash_table_experiments.DataTable(
            id='field_selector_table',
            rows=field_info_table.to_dict('records'),
            columns=['Field'] + [f for f in field_info_table.columns if f!='Field'], #put field first
            row_selectable=True,
            sortable=True,
            selected_row_indices=list(range(len(field_info_table))) #by number, not df index
        )]
else:
    fieldinfo_elements = []

starting_axes_dropdowns = [
    html.Label('X-axis'),
    dcc.Dropdown(
        id='x_dropdown',
        value=None
        # options and value created by callback
    ),
    html.Label('Y-axis'),
    dcc.Dropdown(
        id='y_dropdown',
        value=None
        # options and value created by callback
    )]


app.layout = html.Div(children=[
    #html.H1(children='Data embedding'),

    *fieldinfo_elements,

    # children will be overwritten with stored data
    html.Div(id='hidden_data_div',
             children="",
             style={'display':'none'}),

    html.Label('Scale numeric fields'),
    dcc.RadioItems(
        id='scale_selector',
        options=[{'label':"Scale numeric fields to std=1", 'value':True},
                 {'label':"Leave unscaled", 'value':False}],
        value=False  # TODO: set default to True if any categorical fields?
    ),

    html.Div(id='axis_component_selectors',
             children=starting_axes_dropdowns
    ),

    html.Label('Colour points by'),
    dcc.Dropdown(
        id='colour_dropdown',
        options = [{'label':val,'value':val} for val in ['None']+list(sample_info.columns)],
        value='None'
    ),

    dcc.Graph(
        id='pca-plot',  # No figure - will be generated by callback
        animate=True
    )

])

# Set a different callback depending on whether field_selector_table exists
# Is there a better way?
if args.show_fieldtable:
    @app.callback(
        Output('hidden_data_div', 'children'),
        [Input('field_selector_table','selected_row_indices'),
         Input('scale_selector','value')]
    )
    def update_pca_callback(selected_fields, scale):
        return update_pca(selected_fields, scale)
else:
    @app.callback(
        Output('hidden_data_div', 'children'),
        [Input('scale_selector','value')]
    )
    def update_pca_callback(scale):
        return update_pca(selected_fields=None, scale=scale)

def update_pca(selected_fields, scale):
    """
    Re-do the PCA based on included fields.
    Store in a hidden div.
    """
    print("Updating PCA data")
    if not args.show_fieldtable:
        assert selected_fields is None
        selected_fields = list(range(data.shape[1]))
    pca, transformed = pca_transform(data.iloc[:,selected_fields],
                                     field_info.iloc[selected_fields,:],
                                     max_pcs=args.num_pcs,
                                     scale=scale)
    print("PCA results shape {}".format(transformed.shape))
    return json.dumps({'transformed': transformed.to_json(orient='split'),
                       'variance_ratios': list(pca.explained_variance_ratio_)})

@app.callback(
    Output('axis_component_selectors','children'),
    [Input('hidden_data_div','children')],
    state=[State('x_dropdown','value'), State('y_dropdown','value')]
)
def update_pca_axes(transformed_data_json, previous_x, previous_y):
    """
    When PCA has been updated, re-generate the lists of available axes.
    """
    print("Updating PCA axes dropdowns")
    if transformed_data_json=="":
        print("Data not initialised yet; skipping axes callback")
        return starting_axes_dropdowns
    stored_data = json.loads(transformed_data_json)
    transformed = pd.read_json(stored_data['transformed'], orient='split')
    variance_ratios = stored_data['variance_ratios']
    pca_dropdown_values = [{'label':"{0} ({1:.3} of variance)".format(n,v), 'value':n}
                           for (n,v) in zip(transformed.columns,variance_ratios)]
    # If old selected compontents not available,
    # set x and y to PCA1 and PCA2 respectively
    if previous_x not in transformed.columns:
        previous_x = transformed.columns[0]
    if previous_y not in transformed.columns:
        previous_y = transformed.columns[1]
    new_html = [
        html.Label('X-axis'),
        dcc.Dropdown(
            id='x_dropdown',
            options=pca_dropdown_values,
            value=previous_x
        ),

        html.Label('Y-axis'),
        dcc.Dropdown(
            id='y_dropdown',
            options=pca_dropdown_values,
            value=previous_y
        )]
    return new_html

@app.callback(
    Output('pca-plot','figure'),
    [Input('x_dropdown','value'), Input('y_dropdown','value'),
     Input('colour_dropdown','value')],
    state=[State('hidden_data_div', 'children')]
)
def update_figure(x_field, y_field, colour_field, stored_data):
    # If storing transformed data this way, ought to memoise PCA calculation
    print("Updating figure")
    # Don't try to calculate plot if UI controls not initialised yet
    # Note that we must however return a valid figure specification
    if stored_data=="":
        print("Data not initialised yet; skipping figure callback")
        return {'data': [], 'layout': {'title': 'Calculating plot...'}}
    if x_field is None or y_field is None:
        print("Axes dropdowns not initialised yet; skipping figure callback")
        return {'data': [], 'layout': {'title': 'Calculating plot...'}}
    transformed = pd.read_json(json.loads(stored_data)['transformed'], orient='split')
    if colour_field == 'None':
        traces = [go.Scatter(x=transformed[x_field], y=transformed[y_field],
                  mode='markers', marker=dict(size=10),
                  text=transformed.index)]
    else:
        # Make separate traces to get colours and a legend.
        # Is this the best way?
        traces = []
        for value in sample_info[colour_field].unique():
            rows = sample_info[colour_field] == value
            traces.append(go.Scatter(x=transformed.loc[rows,x_field], y=transformed.loc[rows,y_field],
                          mode='markers', marker=dict(size=10),
                          name=value, text=transformed.index[rows]))
    figure = {
        'data': traces,
        'layout': {
            'title': 'PCA',
            'xaxis': {'title': x_field},
            'yaxis': {'title': y_field},
            'hovermode': 'closest',
        }
    }
    return figure

if __name__ == '__main__':
    app.run_server(debug=True)
