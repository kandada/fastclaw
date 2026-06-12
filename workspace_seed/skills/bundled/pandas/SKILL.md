## Description
Python pandas data analysis. Auto-injects `import pandas as pd; import numpy as np`. Returns DataFrame preview (shape / columns / head).

## Parameters
- code: pandas code string to execute; last expression result included in return value

## Example
run_skills("pandas", {"code": "pd.read_csv('data.csv').head()"})
run_skills("pandas", {"code": "df = pd.DataFrame({'a': [1,2], 'b': [3,4]}); df.describe()"})
