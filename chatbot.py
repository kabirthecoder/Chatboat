import os
import json
import logging
import bcrypt
from pymongo import MongoClient, errors
from together import Together
from email_validator import validate_email, EmailNotValidError
from cryptography.fernet import Fernet
import requests
from cryptography.fernet import Fernet, InvalidToken
import streamlit as st

# Suppress warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Load scenarios from JSON file
with open('scenarios.json', 'r') as f:
    initial_scenarios = json.load(f)['scenarios']



# Define the path to the key file
key_file_path = 'encryption_key.key'

# Generate or load encryption key
if os.path.exists(key_file_path):
    # Load the key from the file
    with open(key_file_path, 'rb') as key_file:
        encryption_key = key_file.read()
else:
    # Generate a new key and save it to the file
    encryption_key = Fernet.generate_key()
    with open(key_file_path, 'wb') as key_file:
        key_file.write(encryption_key)

# Initialize encryption
fernet = Fernet(encryption_key)


# Function to return the fernet instance
def get_fernet():
    return fernet

# Rest of the code...


# Initialize encryption
# fernet = Fernet(os.getenv("ENCRYPTION_KEY"))
class DatabaseHandler:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="mental_health_chatbot"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.users_collection = self.db["users"]
        self.feedback_collection = self.db["feedback"]
        self.ratings_collection = self.db["ratings"]

    def find_user(self, user_id):
        try:
            user = self.users_collection.find_one({"_id": user_id})
            if user:
                # Decrypt user information except for the password
                for key in user:
                    if key not in ["_id", "password", "interactions"]:
                        if isinstance(user[key], str):  # Only decrypt strings
                            try:
                                user[key] = fernet.decrypt(user[key].encode()).decode()
                            except Exception as e:
                                logging.error(f"Decryption failed for key: {key}. Error: {str(e)}")
                                raise Exception(f"Decryption error for {key}")
            return user
        except Exception as e:
            logging.error(f"Error in find_user: {str(e)}")
            raise  # Re-raise the exception to be handled by the caller

    def insert_user(self, user_info):
        # Encrypt other information except the password
        encrypted_info = {
            k: fernet.encrypt(v.encode()).decode() if k not in ["password", "_id"] else v 
            for k, v in user_info.items()
        }

        # Insert the user into the database
        self.users_collection.insert_one(encrypted_info)

    def update_interactions(self, user_id, interaction):
        self.users_collection.update_one(
            {"_id": user_id},
            {"$push": {"interactions": interaction}}
        )

    def insert_feedback(self, feedback_data):
        self.feedback_collection.insert_one(feedback_data)

    def insert_rating(self, rating_data):
        self.ratings_collection.insert_one(rating_data)

    def get_interactions(self, user_id):
        user = self.users_collection.find_one(
            {"_id": user_id}, {"interactions": 1, "_id": 0})
        return user.get('interactions', []) if user else []

class Logger:
    def __init__(self, filename='user_interactions.log'):
        logging.basicConfig(filename=filename, level=logging.INFO,
                            format='%(asctime)s - %(message)s')

    def log_interaction(self, user_input, bot_response):
        interaction = {
            "user_input": user_input,
            "bot_response": bot_response
        }
        logging.info(json.dumps(interaction))

class Chatbot:
    def __init__(self, api_key, db_handler, logger):
        self.api_key = api_key
        self.db_handler = db_handler
        self.logger = logger
        self.session = []
        self.current_scenario = None
        self.awaiting_user_input = False
        self.scenarios = initial_scenarios
        self.scenario_path = []

    def initialize_session(self, user_info):
        system_prompt = f"""You are Neetanshi, a friendly and knowledgeable mental health expert. Your role is to provide support, guidance, and coping strategies for various mental health challenges. Remember to:
    1. Always maintain a supportive and non-judgmental tone
    2. Use active listening techniques in your responses
    3. Incorporate evidence-based strategies like CBT when appropriate
    4. Encourage seeking professional help for serious concerns
    5. Avoid making diagnoses or prescribing medications
    6. Respect user privacy and maintain confidentiality
    7. Adapt your language to the user's age and background
    8. If the user asks any irrelevant questions about anything which is not related to mental health, you will not answer it

    You are interacting with {user_info['name']}, a {user_info['age']}-year-old {user_info['sex']} from {user_info['country']} who works as a {user_info['occupation']}.

    The session is stored as a list of message dictionaries. Each message has a 'role' (system, user, or assistant) and 'content'. This allows you to maintain context throughout the conversation.

    After the first conversation, you should generate new scenarios based on the user's history and context. These scenarios should be in a tree hierarchy structure.

    Always address the user by name and tailor your responses based on their age, location, and occupation."""

        self.session.append({"role": "system", "content": system_prompt})
        self.session.append(
            {"role": "assistant", "content": f"Hello {user_info['name']}! It's great to meet you. As your personal mental health expert, I'm here to listen and offer guidance whenever you need it. Whether you're struggling with anxiety, depression, or something else entirely, I'm here to support you."})

    def generate_response(self, user_input, user_info):
            logging.info(f"Generating response for input: {user_input}")
       
            self.session.append({"role": "user", "content": user_input})

            prompt = f"""
            Task 1: Analyze the sentiment of the input on a scale from -1 (very negative) to 1 (very positive). Do not show the score because the user does not know about this criterion, so use GIFs or emojis accordingly.
            Task 2: Identify the most relevant mental health scenario this input relates to and answer accordingly.
            Task 3: Generate a helpful and empathetic response as Neetanshi, a mental health chatbot. Incorporate CBT techniques if appropriately needed, and add emojis within the chat to help the user feel that you are friendly, but it should be appropriate.

            Before providing your final response, think through these steps:
            1. What is the main concern or emotion expressed by the user?
            2. What might be the underlying cause of this concern?
            3. What coping strategy or technique would be most appropriate?
            4. How can I phrase my response to be most supportive and helpful?

            User Input: {user_input}

            User Info: {user_info['name']}, {user_info['age']}-year-old {user_info['sex']} from {user_info['country']}, occupation: {user_info['occupation']}

            Previous conversation:
            {self.format_conversation_history()}

            Respond in the following format (ensure the Thought Process points are not shown to the user):
            --Sentiment: [appropriate emoji]--
            --Relevant Scenario: [identified scenario]--
            {user_info['name']}: [generated response]
            """
            url = "https://api.together.ai/v1/chat/completions"
            headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            payload = {
                    "model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                    "messages": [{"role": "user", "content": prompt}]
                }
            response = requests.post(url, headers=headers, json=payload)             
            # response = self.client.chat.completions.create(
            #     model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            #     messages=[{"role": "user", "content": prompt}],
            # )

            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("choices"):
                    response_content = response_data["choices"][0]["message"]["content"]
                    self.session.append({"role": "assistant", "content": response_content})
                    self.logger.log_interaction(user_input, response_content)
                    self.db_handler.update_interactions(user_info['_id'], {"user_input": user_input, "bot_response": response_content})

                    # Extract the final response meant for the user
                    final_response = self.extract_final_response(response_content)
                    print(len(self.session))
                    print(final_response)
                    if len(self.session) > 3:
                        self.generate_new_scenarios(user_info)

                    logging.info(f"Generated response: {final_response}")
                    return final_response
        #     else:
        #         logging.error("No response choices returned from the API")
        #         return "I apologize, but I'm having trouble processing your request at the moment. Could you please try again?"
        # except Exception as e:
        #     logging.error(f"Error generating response: {e}")
        #     return "I apologize, but I'm having trouble processing your request at the moment. Could you please try again."

    def extract_final_response(self, response_content):
        # Find the starting index of the final response
        start_idx = response_content.find("Sentiment:")
        if start_idx != -1:
            # Extract the final response
            return response_content[start_idx:].strip()
        return response_content.strip()

    def generate_new_scenarios(self, user_info):
        prompt = f"""Based on the conversation history and user information, generate a new set of mental health scenarios in a tree hierarchy structure. Each scenario should have sub-scenarios. Consider the user's age, occupation, and previous interactions when creating these scenarios. Ensure that the scenarios are relevant to common mental health concerns and tailored to the user's context.

                The structure should be similar to:

                {{
                    "scenario1": {{
                        "prompt": "Main scenario description",
                        "visible": "User-friendly scenario description",
                        "sub_scenarios": {{
                            "sub_scenario1": {{
                                "prompt": "Sub-scenario description",
                                "visible": "User-friendly sub-scenario description"
                            }},
                            "sub_scenario2": {{
                                "prompt": "Sub-scenario description",
                                "visible": "User-friendly sub-scenario description"
                            }}
                        }}
                    }},
                    "scenario2": {{
                        // Similar structure
                    }}
                }}

                User Info: {user_info['name']}, {user_info['age']}-year-old {user_info['sex']} from {user_info['country']}, occupation: {user_info['occupation']}

                Conversation History:
                {self.format_conversation_history()}

                Generate at least 5 main scenarios with 2-3 sub-scenarios each. Ensure that the scenarios cover a range of potential mental health concerns and are phrased in a sensitive, user-friendly manner.

                Generate the scenarios in JSON format.
                """
        new_scenarios = {}
        url = "https://api.together.ai/v1/chat/completions"
        headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
        payload = {
                    "model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
                    "messages": [{"role": "user", "content": prompt}]
                }
        response = requests.post(url, headers=headers, json=payload)    
        
        if response.status_code == 200:
            response_data = response.json()
            
            if response_data.get("choices"):
                # Extract the content which contains the scenarios as a JSON string
                response_content = response_data["choices"][0]["message"]["content"]
                
                # Find the start and end of the JSON part of the content
                start_idx = response_content.find('{')
                end_idx = response_content.rfind('}') + 1
                
                if start_idx != -1 and end_idx != -1:
                    json_str = response_content[start_idx:end_idx]
                    try:
                        # Parse the JSON string into a Python dictionary
                        new_scenarios = json.loads(json_str)
                        # Update the existing scenarios
                        self.scenarios.update(new_scenarios)
                        return new_scenarios
                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to decode JSON from API response: {e}")
                        return {}
                else:
                    logging.error("No valid JSON object found in the response content")
                    return {}
            else:
                logging.error("'choices' key is missing or empty in the API response")
                return {}
        else:
            logging.error(f"API request failed with status code: {response.status_code}")
            return {}
    def handle_user_input(self, user_input, user_info):
        if user_input.lower() in ['exit', 'quit', 'e', 'q']:
            return True

        if self.awaiting_user_input:
            self.awaiting_user_input = False
            current_scenario = self.get_current_scenario()
            sub_scenarios = current_scenario.get('sub_scenarios', {})
            if sub_scenarios:
                sub_scenario_keys = list(sub_scenarios.keys())
                try:
                    selected_index = int(user_input) - 1
                    if 0 <= selected_index < len(sub_scenario_keys):
                        selected_sub_scenario_key = sub_scenario_keys[selected_index]
                        self.scenario_path.append(selected_sub_scenario_key)
                        self.display_sub_scenarios(user_info)
                    else:
                        print("Invalid selection. Please enter a valid number corresponding to an option.")
                        self.display_sub_scenarios(user_info)
                except ValueError:
                    print("Invalid input. Please enter the number corresponding to an option.")
                    self.display_sub_scenarios(user_info)
            return False

        matched_scenario = self.match_scenario(user_input)
        if matched_scenario:
            self.scenario_path = [matched_scenario]
            self.display_sub_scenarios(user_info)
        else:
            print("No matching scenario found. Please try again.")
            self.display_initial_scenarios()

        return False

    def get_current_scenario(self):
        scenario = self.scenarios
        for key in self.scenario_path:
            scenario = scenario['sub_scenarios'][key]
        return scenario

    def match_scenario(self, input_text):
        prompt = f"""Given the user input, identify the most relevant scenario from the following options:

        Scenarios: {json.dumps(self.scenarios)}

        User Input: {input_text}

        Return only the key of the most relevant scenario.
        """

        response = self.client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content.strip()

    def display_sub_scenarios(self, user_info):
        current_scenario = self.get_current_scenario()
        if 'sub_scenarios' in current_scenario:
            sub_scenarios = current_scenario['sub_scenarios']
            print("\nHere are some related questions you might find helpful:")
            for i, key in enumerate(sub_scenarios, 1):
                print(f"{i}. {sub_scenarios[key]['visible']}")
            self.awaiting_user_input = True
        else:
            response = self.generate_response(' '.join(self.scenario_path), user_info)
            print("Neetanshi:", response)

    def display_initial_scenarios(self):
        initial_scenarios = [scenario["visible"] for scenario in self.scenarios.values()]
        for i, scenario in enumerate(initial_scenarios, 1):
            print(f"{i}. {scenario}")

    def format_conversation_history(self):
        history = ""
        for message in self.session:
            role = message["role"]
            content = message["content"]
            if role == "assistant":
                lines = content.split("\n")
                filtered_lines = [line for line in lines if not line.startswith("Thought Process:")]
                filtered_content = "\n".join(filtered_lines)
                history += f"{role}: {filtered_content}\n"
            elif role == "user":
                history += f"{role}: {content}\n"
        return history



class UserHandler:
    def __init__(self, db_handler):
        self.db_handler = db_handler

    def collect_user_info(self, new_user=True):
        user_info = {}
        if new_user:
            user_info['name'] = input("What's your name?\n> ")
            user_info['occupation'] = input("What's your occupation?\n> ")
            user_info['age'] = input("How old are you?\n> ")
            user_info['sex'] = input(
                "What's your sex (male/female/other)?\n> ")
            user_info['country'] = input("Which country are you from?\n> ")

            while True:
                email = input("What's your email address?\n> ")
                try:
                    v = validate_email(email)
                    user_info['email'] = v.email
                    if self.db_handler.find_user(user_info['email'].lower()):
                        print(
                            "This email address is already registered. Please log in instead.")
                        return self.collect_user_info(new_user=False)
                    break
                except EmailNotValidError as e:
                    print(str(e))

            password = input("Create a password:\n> ")
            hashed_password = bcrypt.hashpw(
                password.encode('utf-8'), bcrypt.gensalt())
            user_info['password'] = hashed_password
            user_info['_id'] = user_info['email'].lower()

            try:
                self.db_handler.insert_user(user_info)
            except errors.DuplicateKeyError:
                print("This email address is already registered. Please log in instead.")
                return self.collect_user_info(new_user=False)
        else:
            email = input("What's your email address?\n> ")
            password = input("Enter your password:\n> ")
            user_info = self.db_handler.find_user(email.lower())
            if user_info and bcrypt.checkpw(password.encode('utf-8'), user_info['password']):
                print(f"Welcome back, {user_info['name']}!")
            else:
                print("Invalid email or password. Please try again.")
                return self.collect_user_info(new_user=False)

        return user_info

    def collect_rating_and_feedback(self, user_id):
        def collect_rating():
            rating = input(
                "Please rate your experience with the chatbot (1 to 5):\n> ")
            try:
                rating_value = int(rating)
                if 1 <= rating_value <= 5:
                    rating_data = {
                        "user_id": user_id,
                        "rating": rating_value
                    }
                    self.db_handler.insert_rating(rating_data)
                    print("Thank you for your rating!")
                else:
                    print("Invalid rating. Please enter a number between 1 and 5.")
                    collect_rating()
            except ValueError:
                print("Invalid rating. Please enter a number between 1 and 5.")
                collect_rating()

        def collect_feedback():
            feedback = input(
                "Please provide your feedback on the chatbot experience:\n> ")
            feedback_data = {
                "user_id": user_id,
                "feedback": feedback
            }
            try:
                self.db_handler.insert_feedback(feedback_data)
                print("Thank you for your feedback!")
            except errors.PyMongoError as e:
                logging.error(f"Error collecting feedback: {e}")
                print(
                    "Sorry, there was an error collecting your feedback. Please try again later.")

        collect_rating()
        collect_feedback()

def main():
    db_handler = DatabaseHandler()
    logger = Logger()
    user_handler = UserHandler(db_handler)
    chatbot = Chatbot(api_key="6abe6cd1c19a11f9919847e8deae4040d04701b7c1916eabc06d855fdfaff639",
                      db_handler=db_handler, logger=logger)

    have_account = input(
        "Do you have an account with Neetanshi? (yes/no)\n> ").strip().lower()
    if have_account == "yes":
        user_info = user_handler.collect_user_info(new_user=False)
    else:
        user_info = user_handler.collect_user_info(new_user=True)

    chatbot.initialize_session(user_info)

    print(
        f"Welcome to Neetanshi, {user_info['name']}! Your mental health chatbot.")
    print("Please select a scenario by entering the corresponding number or type your own scenario:")

    chatbot.display_initial_scenarios()

    while True:
        user_input = input("> ")
        if user_input.lower() in ['exit', 'quit', 'e', 'q']:
            print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
            user_handler.collect_rating_and_feedback(user_info['_id'])
            print("Goodbye! Take care.")
            break

        should_exit = chatbot.handle_user_input(user_input, user_info)
        if should_exit:
            break

        if not chatbot.awaiting_user_input:
            print(
                "\nYou can continue the conversation or type 'exit' to end the session.")

    print("Goodbye! Take care.")

if __name__ == "__main__":
    main()
