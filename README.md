# Chatbot Project

## Overview
This project consists of a chatbot designed to interact with users experiencing various emotional and mental health issues. The chatbot uses predefined scenarios to guide conversations and provide support based on user input.

## Project Structure
- **ui1.py**: Contains the user interface code for interacting with the chatbot.
- **chatbot.py**: Contains the core logic and functionalities of the chatbot, including how it processes user input and navigates through different scenarios.
- **scenarios.json**: A structured file that outlines different conversational scenarios the chatbot can handle. It includes nested scenarios to address a wide range of user concerns.
- **user_interactions.log**: Logs the interactions between users and the chatbot for further analysis and improvement.

## Scenarios
The `scenarios.json` file contains a comprehensive set of scenarios that the chatbot can use to guide conversations. Some key scenarios include:
- Anxiety
- Trouble sleeping
- Overwhelming workload
- Relationship problems
- Loneliness and isolation
- Depression
- Panic attacks
- Grief and loss

Each scenario can branch into sub-scenarios, allowing for deeper exploration of the user's feelings and experiences. 

### Example Structure
A scenario is structured with prompts and visible text to guide the conversation. For instance, the "I am feeling very anxious lately" scenario contains sub-scenarios like "Can you tell me more about what is making you feel anxious?" and "Do you experience physical symptoms as well?".

## Getting Started
1. **Installation**: Ensure you have the necessary Python libraries installed to run the chatbot and UI scripts.
2. **Running the Chatbot**:
   - Execute `frontend.py` to start the user interface.
   - The chatbot will use `chatbot.py` to process interactions.
3. **Using the Scenarios**: The chatbot utilizes the `scenarios.json` file to navigate conversations based on user input. Modify this file to add or update conversational paths.

## How It Works
- The chatbot starts with a general question or statement and uses user responses to navigate through different scenarios.
- Each user input triggers a search within the scenario structure to find the most relevant follow-up prompt.

## Contributing
Contributions to this project are welcome. To add new scenarios, update the `scenarios.json` file following the existing structure.

## License
This project is licensed under [LICENSE](./LICENSE).
