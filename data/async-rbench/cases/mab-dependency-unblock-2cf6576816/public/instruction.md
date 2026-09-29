Software Development Task:

Please write a program called MultiServe that facilitates a collaborative food ordering and delivery system for a network of restaurants and delivery agents. MultiServe is a software application that enables users to order food from multiple restaurants simultaneously, and it coordinates the delivery process by assigning tasks to multiple delivery agents to ensure efficient and timely delivery.
1. Implementation requirements:
   - Implement a user interface where users can browse menus from multiple restaurants, add items to a cart, and place a single order that combines items from different restaurants.
   - Develop a backend system that can handle the coordination of orders from multiple restaurants, including sending order details to each restaurant and tracking the status of each order.
   - Create a delivery agent interface that allows multiple delivery agents to log in, receive assigned delivery tasks, and update the status of their deliveries in real-time.
   - Design a comprehensive set of test cases to validate the functionality of the system, including the following scenarios:
   -  - A user places an order with items from two different restaurants, and the system correctly sends the order details to both restaurants.
   -  - The system assigns the delivery tasks to two different delivery agents, and both agents receive the correct delivery details.
   -  - The system updates the order status in real-time as each delivery agent completes their part of the delivery.
   -  - The system handles edge cases such as a restaurant being unavailable, a delivery agent declining a task, or a user canceling an order after it has been placed.
   -  - The system ensures that the user receives a notification when the order is ready for pickup or has been delivered.


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
Persist cart, restaurant, agent, and provisional order state while the logistics child has failed implicitly. The harness then delivers recovered suborder, aggregate-status, grouping, and assignment rules. Re-delegate the failed dependency, revise only logistics outputs, preserve cancellation and restaurant decisions, and reverify the full delivery lifecycle.
