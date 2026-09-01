Software Development Task:

Please write a system called DataFlowCoordinator that manages and coordinates the processing of data through multiple stages, ensuring data integrity and quality at each step. DataFlowCoordinator is a data processing system that orchestrates the flow of data through various stages, including data ingestion, validation, transformation, and export, ensuring that each stage is completed successfully before moving on to the next.
1. Implementation requirements:
   - 1. **Data Ingestion Module**: Develop a module to ingest data from various sources such as CSV, Excel, and database connections. This module must be capable of handling large datasets and should validate the data format upon ingestion.
   - 2. **Data Validation Module**: Create a module that performs comprehensive data validation, including checks for data consistency, accuracy, completeness, and validity. This module must be executed after the data ingestion module to ensure that the data is clean and ready for further processing.
   - 3. **Data Transformation Module**: Implement a module that allows users to define and apply transformation rules to the data, such as changing data types, rearranging columns, removing duplicates, and merging cells. This module should only be activated after the data validation module has confirmed the data's integrity.
   - 4. **Data Export Module**: Develop a module to export the processed data to various formats, including CSV, Excel, and database tables. This module should only be executed after the data transformation module has completed its tasks.
   - 5. **Dependency Management**: Ensure that the system enforces the correct order of operations, where the data ingestion module must complete before the data validation module starts, the data validation module must complete before the data transformation module starts, and the data transformation module must complete before the data export module starts.


2. Project structure:
   - solution.py (main implementation)

3. Development process:
   - Developer: Create the code.
   - Developer: Revise the code.
   - Developer: Optimize the code.

If there are multiple files, please put them all in solution.py, but remember to add the file name in the following format:
```python
# file_name_1.py
# your code here

# file_name_2.py
# your code here

# file_name_3.py
# your code here
```

Please work together to complete this task following software engineering best practices.

The final deliverable should include:
solution.py

ASYNC-RBENCH EXTENSION
Persist the common ingestion stream and export scaffolding while validation is pending. The harness then delivers a validation completion that may be replayed. Deduplicate that completion, transform accepted rows exactly once, keep rejected rows out of transformation/export, and close with receipt-bound evidence.
