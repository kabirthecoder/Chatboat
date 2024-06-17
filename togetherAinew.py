import os
import json
import logging
import bcrypt
from pymongo import MongoClient, errors
from together import Together
from transformers import pipeline
from email_validator import validate_email, EmailNotValidError

# Suppress warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Initialize Together client with API key
api_key = "b5f35af32c4170f17fc17b376e07f27f2639eca7ba1d77b9990eee6704042f08"
client = Together(api_key=api_key)

# Configure logging
logging.basicConfig(filename='user_interactions.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Initialize the text classification pipeline with a lightweight model
classifier = pipeline("text-classification", model="distilbert-base-uncased-finetuned-sst-2-english")

# MongoDB connection setup
mongo_uri = "mongodb://localhost:27017/"
mongo_client = MongoClient(mongo_uri)
db = mongo_client["mental_health_chatbot"]
users_collection = db["users"]

# Secret key for session management (if needed)
secret_key = "your_secret_key"

# Tree-like structure for scenarios and follow-up questions
scenarios = {
    "I am feeling very anxious lately.": {
        "Can you tell me more about what is making you feel anxious?": {
            "Is it related to work or personal life?": {
                "Work": {},
                "Personal life": {}
            },
            "Do you experience physical symptoms as well?": {
                "Yes": {},
                "No": {}
            }
        },
        "How long have you been feeling this way?": {
            "A few days": {},
            "More than a week": {}
        }
    },
    "I am having trouble sleeping at night.": {
        "Have you noticed any patterns or habits that might be affecting your sleep?": {
            "Caffeine intake": {},
            "Screen time before bed": {}
        },
        "Do you feel stressed or worried when you go to bed?": {
            "Yes, very stressed": {},
            "No, just can't sleep": {}
        }
    },
    "I feel overwhelmed with my workload.": {
        "What tasks are causing you the most stress?": {
            "High-priority tasks": {},
            "Volume of tasks": {}
        },
        "How do you currently manage your workload?": {
            "Prioritization": {},
            "Time management": {}
        }
    },
    "I am experiencing relationship problems.": {
        "Can you describe the issues you are facing in your relationship?": {
            "Communication issues": {},
            "Trust issues": {}
        },
        "How long have you been experiencing these problems?": {
            "Recently": {},
            "For a long time": {}
        }
    },
    "I have been feeling very lonely and isolated.": {
        "Have you been able to connect with friends or family?": {
            "Yes, but still feel lonely": {},
            "No, I haven't tried": {}
        },
        "What activities do you enjoy that might help you feel less isolated?": {
            "Hobbies": {},
            "Social gatherings": {}
        }
    }
}

# Function to log and save interaction
def log_interaction(user_input, bot_response, user_id):
    interaction = {
        "user_input": user_input,
        "bot_response": bot_response
    }
    logging.info(json.dumps(interaction))
    try:
        users_collection.update_one(
            {"_id": user_id},
            {"$push": {"interactions": interaction}}
        )
    except errors.PyMongoError as e:
        logging.error(f"Error logging interaction: {e}")

# Function to generate a response based on user input and profile
def generate_response(session, user_input, user_info):
    session.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="meta-llama/Llama-3-70b-chat-hf",
        messages=session,
    )
    response_content = response.choices[0].message.content
    
    # Add age-specific considerations
    age = int(user_info['age'])
    if age < 18:
        response_content += "\n\nAs you are a minor, it's important to discuss your feelings and any issues you have with a trusted adult, such as a parent, guardian, or school counselor."
    
    # Add country-specific considerations
    country = user_info['country'].lower()
    if country == 'usa':
        response_content += "\n\nIn the United States, there are many resources available for mental health support, including hotlines and online services. If you need immediate help, consider reaching out to a mental health professional."
    elif country == 'india':
        response_content += "\n\nIn India, there are several organizations that provide mental health support, including helplines and counseling services. It's important to reach out to these resources if you need assistance."
    # Add more country-specific guidelines as needed

    session.append({"role": "assistant", "content": response_content})
    log_interaction(user_input, response_content, user_info['_id'])
    return response_content

# Function to navigate the scenario tree
def navigate_scenario_tree(scenario_tree, session, user_info):
    if not scenario_tree:
        return
    options = list(scenario_tree.keys())
    while options:
        selected_option = display_options(options, allow_custom=False)
        if selected_option in scenario_tree:
            response = generate_response(session, selected_option, user_info)
            print("Neetanshi:", response)
            navigate_scenario_tree(scenario_tree[selected_option], session, user_info)
            break

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
    return "mental health" in input_text.lower() or results[0]['label'] == 'NEGATIVE' or 'fight' in input_text.lower()

# Function to handle user input and provide related follow-up questions
def handle_user_input(session, user_input, related_questions, user_info):
    if user_input.lower() in ['exit', 'quit', '1']:
        print("Goodbye! Take care.")
        return True

    if not is_mental_health_related(user_input):
        response = "Sorry, I am here for mental health-related topics. Do you have any questions or issues related to mental health?"
        print("Neetanshi:", response)
        log_interaction(user_input, response, user_info['_id'])
        return False

    response = generate_response(session, user_input, user_info)
    print("Neetanshi:", response)
    if related_questions:
        print("\nHere are some related questions you might find helpful:")
        options = list(related_questions.keys())
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        print(f"{len(options) + 1}. Enter your own question or concern")
        next_input = input("> ")
        try:
            option_index = int(next_input) - 1
            if 0 <= option_index < len(options):
                selected_question = options[option_index]
                return handle_user_input(session, selected_question, related_questions[selected_question], user_info)
            elif option_index == len(options):
                user_input = input("Please enter your own question or concern:\n> ")
                return handle_user_input(session, user_input, {}, user_info)
            else:
                print("Invalid selection. Please enter a number corresponding to an option.")
        except ValueError:
            print("Invalid input. Please enter a number.")
    else:
        print("Please provide more details or ask another question (type 'exit' to quit or 'scenario' to select another topic):")
        next_input = input("> ")
        if next_input.lower() in ['exit', 'quit']:
            print("Goodbye! Take care.")
            return True
        elif next_input.lower() == 'scenario':
            return False
        else:
            return handle_user_input(session, next_input, {}, user_info)

# Function to collect user information
def collect_user_info(new_user=True):
    user_info = {}
    if new_user:
        user_info['name'] = input("What's your name?\n> ")
        user_info['occupation'] = input("What's your occupation?\n> ")
        user_info['age'] = input("How old are you?\n> ")
        user_info['sex'] = input("What's your sex (male/female/other)?\n> ")
        user_info['country'] = input("Which country are you from?\n> ")

        while True:
            email = input("What's your email address?\n> ")
            try:
                v = validate_email(email)
                user_info['email'] = v.email
                if users_collection.find_one({"_id": user_info['email'].lower()}):
                    print("This email address is already registered. Please log in instead.")
                    return collect_user_info(new_user=False)
                break
            except EmailNotValidError as e:
                print(str(e))
        
        password = input("Create a password:\n> ")
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user_info['password'] = hashed_password
        user_info['_id'] = user_info['email'].lower()
        
        try:
            users_collection.insert_one(user_info)
        except errors.DuplicateKeyError:
            print("This email address is already registered. Please log in instead.")
            return collect_user_info(new_user=False)
    else:
        email = input("What's your email address?\n> ")
        password = input("Enter your password:\n> ")
        user_info = users_collection.find_one({"_id": email.lower()})
        if user_info and bcrypt.checkpw(password.encode('utf-8'), user_info['password']):
            print(f"Welcome back, {user_info['name']}!")
        else:
            print("Invalid email or password. Please try again.")
            return collect_user_info(new_user=False)
    
    return user_info

# Main interaction loop
def main():
    session = []

    # Ask user if they have an account
    have_account = input("Do you have an account with Neetanshi? (yes/no)\n> ").strip().lower()
    if have_account == "yes":
        user_info = collect_user_info(new_user=False)
    else:
        user_info = collect_user_info(new_user=True)

    # Add initial messages only if the session is empty
    if not session:
        session.append({"role": "system", "content": f"You are Neetanshi, a friendly and knowledgeable mental health expert. Your role is to provide support, guidance, and coping strategies for various mental health challenges and situations that impact one's well-being. You are interacting with {user_info['name']}, a {user_info['age']}-year-old {user_info['sex']} from {user_info['country']} who works as a {user_info['occupation']}."})
        session.append({"role": "assistant", "content": f"Hello {user_info['name']}! It's great to meet you. As your personal mental health expert, I'm here to listen and offer guidance whenever you need it. Whether you're struggling with anxiety, depression, or something else entirely, I'm here to support you."})

    print(f"Welcome to Neetanshi, {user_info['name']}! Your mental health chatbot.")
    print("Please select a scenario by entering the corresponding number or type your own scenario:")

    initial_scenarios = list(scenarios.keys())
    selected_scenario = display_options(initial_scenarios, allow_custom=True)

    while selected_scenario and selected_scenario.lower() != "exit":
        if selected_scenario.lower() == "who are you":
            response = f"I am Neetanshi, your mental health expert. How can I assist you with your mental health today, {user_info['name']}?"
            print("Neetanshi:", response)
            log_interaction(selected_scenario, response, user_info['_id'])
        else:
            should_exit = handle_user_input(session, selected_scenario, scenarios.get(selected_scenario, {}), user_info)
            if should_exit:
                break

    print("Goodbye! Take care.")

if __name__ == "__main__":
    main()
