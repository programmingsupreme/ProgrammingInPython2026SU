import pandas as pd
# Load sample CSV data
#Lab 1 Software Installation
df = pd.read_csv('sample.csv')
# Display basic information
print(df.info())
# Display the first 5 rows of the dataframe
print(df.head())