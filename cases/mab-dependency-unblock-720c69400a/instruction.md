Software Development Task:

Please write a program called PriceTrackerCollaborator that enables multiple users to collaboratively track and manage price alerts for products they are interested in purchasing. PriceTrackerCollaborator is a web-based application that allows users to set price thresholds for specific products, receive notifications when prices drop, and share these alerts with other users in a group or community setting. The application also provides insights on the best time to make a purchase and allows users to compare prices across different online retailers.
1. Implementation requirements:
   - The application should allow users to register and log in using their email and a password.
   - Users should be able to create a group or join existing groups to share price alerts with other users.
   - Each user should be able to add products to their watchlist by entering the product URL or by searching for the product within the application.
   - For each product, users should be able to set a price threshold and receive notifications when the price drops below this threshold.
   - The application should provide real-time price updates for the products in the watchlist and notify users via email or in-app notifications.
   - Users should be able to share price alerts within their group, and group members should receive notifications about the shared alerts.
   - The application should have a feature to compare prices across different online retailers for the same product.
   - The application should provide insights on historical price trends and suggest the best time to make a purchase.
   - Comprehensive test cases should be defined, including input scenarios such as adding a product, setting a price threshold, receiving notifications, sharing alerts, and comparing prices.
   - Test cases should also cover edge cases such as invalid URLs, non-existent products, and handling of multiple price thresholds for the same product.
   - The application should handle concurrent access from multiple users and ensure data consistency and integrity.


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
Persist users, groups, watchlists, thresholds, sharing, and provisional single-price alerts while the retailer child has failed implicitly. The harness then delivers normalized multi-retailer quotes. Re-delegate the failed dependency, convert comparable currencies, select the best fresh available quote, preserve group sharing, and reverify alert and comparison behavior.
