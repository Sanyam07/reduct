
import pandas as pd
import numpy as np
from sklearn.decomposition import PCA


def complete_missing_data(data, field_info,
                          method='fill_values',
                          numeric_fill='mean',
                          categorical_fill='common_unknown'):
    """
    Fill in missing values, or delete rows/columns, to produce
    a dataset with no missing values.
    Allowed methods:
        drop_fields: drop fields with any missing values
        drop_samples: drop samples with any missing values
        fill_values: fill in missing values
    If fill_values, numeric_fill and categorical_fill will be used -
    otherwise these fields are ignored.
    Allowed numeric_fill values:
        zeroes: fill in with zeroes (rarely useful)
        mean: fill in with the mean of that column
    Allowed categorical_fill values:
        common_unknown: fill in with a single new "Unknown" category
        unique_unknown: fill in each missing value with a unique category
                        This prevents unknowns from clustering together artificially

    Returns (completed, fields_kept, samples_kept)
    where completed is the modified data array
          fields_kept is a boolean of the original fields
          samples_kept is a boolean of the original samples
    """
    if method=='drop_fields':

        fields_kept = data.isnull().sum() == 0
        completed = data.loc[:,fields_kept]
        samples_kept = pd.Series(True, index=data.index)

    elif method=='drop_samples':

        samples_kept = data.isnull().sum(axis=1) == 0
        completed = data.loc[samples_kept,:]
        fields_kept = pd.Series(True, index=field_info.index)  # same as data.columns

    elif method=='fill_values':

        if numeric_fill not in "zeroes mean".split():
            raise ValueError("Unknown missing value method for numeric fields: "+numeric_fill)
        if categorical_fill not in "common_unknown unique_unknown".split():
            raise ValueError("Unknown missing value method for categorical fields: "+categorical_fill)

        fields_kept = pd.Series(True, index=field_info.index)  # same as data.columns
        samples_kept = pd.Series(True, index=data.index)

        data_missing = data.isnull().sum() > 0
        numeric = field_info['FieldType']=='Numeric'
        categorical = field_info['FieldType']=='Categorical'
        numeric_fields = data.columns[data_missing & numeric]
        categorical_fields = data.columns[data_missing & categorical]

        completed = data.copy()

        for field in numeric_fields:
            print("Filling in missing values in "+field)
            missing_values = data[field].isnull()
            if numeric_fill=='zeroes':
                completed.loc[missing_values,field] = 0
            elif numeric_fill=='mean':
                completed.loc[missing_values,field] = data[field].mean()

        for field in categorical_fields:
            print("Filling in missing values in "+field)
            missing_values = data[field].isnull()
            if categorical_fill=='common_unknown':
                print("Common unknown")
                new_value = 'Unknown'
                # Make sure this value does not already exist in data
                while new_value in data[field].unique():
                    new_value = new_value + "_"
                completed.loc[missing_values,field] = new_value
            elif categorical_fill=='unique_unknown':
                print("Unique unknown")
                new_values = ["Unknown{}".format(n+1) for n in range(missing_values.sum())]
                # Make sure none of these values already exist in data
                while data[field].isin(new_values).sum() > 0:
                    new_values = [v+"_" for v in new_values]
                completed.loc[missing_values,field] = new_values

    else:
        raise ValueError("Unknown missing data method "+method)

    print("Data shape after missing data handling: {}".format(completed.shape))
    #print(completed.head(10))
    return (completed, fields_kept, samples_kept)

def one_hot(series, categories=None):
    """
    Given a series of M categorical values,
    with N categories,
    return a binary-encoded MxN DataFrame of 0's and 1's,
    where each column corresponds to a category.
    The category name is encoded in the columns of the returned DataFrame,
    i.e. each column name is of form {OriginalFieldName}_{CategoryName}.
    """
    if categories is None:
        vec = series.astype('category')
    else:
        vec = series.astype('category', categories=categories)
    vec_numeric = vec.cat.codes
    encoded = pd.DataFrame(np.eye(len(vec.cat.categories), dtype=int)[vec_numeric])
    encoded.columns = ['{}_{}'.format(series.name, c) for c in vec.cat.categories]
    encoded.index = vec.index
    return encoded

def pca_transform(data, field_info, max_pcs, scale=False):
    """
    Apply PCA to the data. There must be no missing values.
    Returns a tuple containing:
        the pca object,
        the transformed data,
        the labelled components, and
        a dict mapping one-hot-encoded field names to original fields.
    """
    numeric_fieldspec = field_info['FieldType']=='Numeric'
    categorical_fields = data.columns[field_info['FieldType']=='Categorical']

    if scale:
        # Subtracting mean should have no effect,
        # dividing by std should
        data.loc[:,numeric_fieldspec] -= data.loc[:,numeric_fieldspec].mean()
        data.loc[:,numeric_fieldspec] /= data.loc[:,numeric_fieldspec].std()

    # Encode any categorical fields, and concat results with numerical fields
    # For now, handling only unordered categories
    encoded_field_list = [one_hot(data[field]) for field in categorical_fields]
    encoded = pd.concat([data.loc[:,numeric_fieldspec]] +
                        encoded_field_list,
                        axis=1)

    print("One-hot encoded data shape {}".format(encoded.shape))
    assert np.all(data.index==encoded.index)

    # Do PCA
    num_pcs = min(max_pcs, encoded.shape[1], encoded.shape[0])
    pca = PCA(num_pcs)
    transformed = pd.DataFrame(pca.fit_transform(encoded.as_matrix()), index=encoded.index)
    pca_names = ["PCA{}".format(n) for n in range(1,num_pcs+1)]
    transformed.columns = pca_names

    # Store components with consistent naming scheme
    components = pd.DataFrame(pca.components_.transpose())
    components.columns = pca_names
    components.index = encoded.columns
    original_fields = {}
    for field in data.columns[numeric_fieldspec]:
        original_fields[field] = field
    for (field,ef) in zip(categorical_fields,encoded_field_list):
        for encoded_column in ef.columns:
            original_fields[encoded_column] = field

    # pca object, pca-transformed data, one-hot-encoded fieldnames, one-hot-encoded original fields
    return (pca, transformed, components, original_fields)#, list(encoded.columns))
