import os
import json
import logging
from together import Together
from transformers import pipeline

# Initialize Together client with API key
api_key = "b5f35af32c4170f17fc17b376e07f27f2639eca7ba1d77b9990eee6704042f08"
client = Together(api_key=api_key)

# Configure logging
logging.basicConfig(filename='user_interactions.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Initialize the text classification pipeline with a lightweight model
classifier = pipeline("text-classification", model="distilbert-base-uncased-finetuned-sst-2-english")

# Tree-like structure for scenarios and follow-up questions
scenarios = {
    "I am feeling very anxious lately.": {
        "Can you tell me more about what is making you feel anxious?": {},
        "How long have you been feeling this way?": {}
    },
    "I am having trouble sleeping at night.": {
        "Have you noticed any patterns or habits that might be affecting your sleep?": {},
        "Do you feel stressed or worried when you go to bed?": {}
    },
    "I feel overwhelmed with my workload.": {
        "What tasks are causing you the most stress?": {},
        "How do you currently manage your workload?": {}
    },
    "I am experiencing relationship problems.": {
        "Can you describe the issues you are facing in your relationship?": {},
        "How long have you been experiencing these problems?": {}
    },
    "I have been feeling very lonely and isolated.": {
        "Have you been able to connect with friends or family?": {},
        "What activities do you enjoy that might help you feel less isolated?": {}
    }
}

# Function to log and save interaction
def log_interaction(user_input, bot_response):
    interaction = {
        "user_input": user_input,
        "bot_response": bot_response
    }
    logging.info(json.dumps(interaction))

# Function to get response from the chatbot
def get_response(session, user_input):
    session.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="meta-llama/Llama-3-70b-chat-hf",
        messages=session,
    )
    response_content = response.choices[0].message.content
    session.append({"role": "assistant", "content": response_content})
    log_interaction(user_input, response_content)
    return response_content

# Function to display options and handle user input
def display_options(options, allow_custom=False):
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")
    if allow_custom:
        print(f"{len(options) + 1}. Enter your own scenario or problem")
    user_input = input("> ")
    try:
        option_index = int(user_input) - 1
        if 0 <= option_index < len(options):
            return options[option_index]
        elif allow_custom and option_index == len(options):
            return input("Please enter your own scenario or problem:\n> ")
        else:
            print("Invalid selection. Please enter a number corresponding to an option.")
            return None
    except ValueError:
        print("Invalid input. Please enter a number.")
        return None

# Function to check if the user input is related to mental health using a pre-trained NLP model
def is_mental_health_related(input_text):
    results = classifier(input_text)
    # Check if the sentiment is negative, which often correlates with mental health-related issues
    return results[0]['label'] == 'NEGATIVE'

# Main interaction loop
def main():
    session = []

    # Add initial messages only if the session is empty
    if not session:
        session.append({"role": "system", "content": "You are Neetanshi, a friendly and knowledgeable mental health expert. Your role is to provide support, guidance, and coping strategies for various mental health challenges and situations that impact one's well-being."})
        session.append({"role": "assistant", "content": "Hello there! It's great to meet you. As your personal mental health expert, I'm here to listen and offer guidance whenever you need it. Whether you're struggling with anxiety, depression, or something else entirely, I'm here to support you."})

    print("Welcome to Neetanshi, your mental health chatbot.")
    print("Please select a scenario by entering the corresponding number or type your own scenario:")

    initial_scenarios = list(scenarios.keys())
    selected_scenario = display_options(initial_scenarios, allow_custom=True)

    while selected_scenario and selected_scenario.lower() != "exit":
        if selected_scenario.lower() == "who are you":
            response = "I am Neetanshi, your mental health expert. How can I assist you with your mental health today?"
            print("Neetanshi:", response)
            log_interaction(selected_scenario, response)
        elif not is_mental_health_related(selected_scenario):
            response = "Sorry, I am here for mental health-related topics. Do you have any questions or issues related to mental health?"
            print("Neetanshi:", response)
            log_interaction(selected_scenario, response)
        else:
            response = get_response(session, selected_scenario)
            print("Neetanshi:", response)

            while True:
                user_input = input("Please provide more details or ask another question (type 'exit' to quit or 'scenario' to select another topic):\n> ")
                if user_input.lower() == 'exit':
                    selected_scenario = 'exit'
                    break
                elif user_input.lower() == 'scenario':
                    selected_scenario = display_options(initial_scenarios, allow_custom=True)
                    break
                else:
                    if is_mental_health_related(user_input):
                        response = get_response(session, user_input)
                        print("Neetanshi:", response)
                    else:
                        response = "Sorry, I am here for mental health-related topics. Do you have any questions or issues related to mental health?"
                        print("Neetanshi:", response)
                        log_interaction(user_input, response)

    print("Goodbye! Take care.")

if __name__ == "__main__":
    main()
