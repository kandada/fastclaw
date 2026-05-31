## Description
Python numpy numerical computing. Auto-injects `import numpy as np`.

## Parameters
- code: numpy code string to execute; last expression result included in return value

## Example
run_skills("numpy", {"code": "np.array([1,2,3]).mean()"})
run_skills("numpy", {"code": "a = np.random.randn(1000); a.mean(), a.std()"})
