import os
import json
import logging
import bcrypt
from pymongo import MongoClient, errors
from together import Together
from email_validator import validate_email, EmailNotValidError

# Suppress warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

class DatabaseHandler:
    def __init__(self, uri="mongodb://localhost:27017/", db_name="mental_health_chatbot"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.users_collection = self.db["users"]
        self.feedback_collection = self.db["feedback"]
        self.ratings_collection = self.db["ratings"]

    def find_user(self, user_id):
        return self.users_collection.find_one({"_id": user_id})

    def insert_user(self, user_info):
        self.users_collection.insert_one(user_info)

    def update_interactions(self, user_id, interaction):
        self.users_collection.update_one(
            {"_id": user_id},
            {"$push": {"interactions": interaction}}
        )

    def insert_feedback(self, feedback_data):
        self.feedback_collection.insert_one(feedback_data)

    def insert_rating(self, rating_data):
        self.ratings_collection.insert_one(rating_data)


class Logger:
    def __init__(self, filename='user_interactions.log'):
        logging.basicConfig(filename=filename, level=logging.INFO, format='%(asctime)s - %(message)s')

    def log_interaction(self, user_input, bot_response):
        interaction = {
            "user_input": user_input,
            "bot_response": bot_response
        }
        logging.info(json.dumps(interaction))


class Chatbot:
    def __init__(self, api_key, db_handler, logger):
        self.client = Together(api_key=api_key)
        self.db_handler = db_handler
        self.logger = logger
        self.session = []
        self.last_question = None  # Track the last question asked

    def generate_response(self, user_input, user_info):
        self.session.append({"role": "user", "content": user_input})
        response = self.client.chat.completions.create(
            model="meta-llama/Llama-3-70b-chat-hf",
            messages=self.session,
        )
        response_content = response.choices[0].message.content

        age = int(user_info['age'])
        if age < 18:
            response_content += "\n\nAs you are a minor, it's important to discuss your feelings and any issues you have with a trusted adult, such as a parent, guardian, or school counselor."

        country = user_info['country'].lower()
        if country == 'usa':
            response_content += "\n\nIn the United States, there are many resources available for mental health support, including hotlines and online services. If you need immediate help, consider reaching out to a mental health professional."
        elif country == 'india':
            response_content += "\n\nIn India, there are several organizations that provide mental health support, including helplines and counseling services. It's important to reach out to these resources if you need assistance."
        elif country == 'germany':
            response_content += "\n\nIn Germany, there are numerous resources for mental health support, including helplines and counseling services. If you need help, consider reaching out to a mental health professional or a trusted organization."

        self.session.append({"role": "assistant", "content": response_content})
        self.logger.log_interaction(user_input, response_content)
        self.db_handler.update_interactions(user_info['_id'], {"user_input": user_input, "bot_response": response_content})
        return response_content

    def is_mental_health_related(self, input_text):
        response = self.client.chat.completions.create(
            model="meta-llama/Llama-3-70b-chat-hf",
            messages=[{"role": "user", "content": f"Is the following text related to mental health? {input_text}"}],
        )
        response_content = response.choices[0].message.content
        return "yes" in response_content.lower()


class UserHandler:
    def __init__(self, db_handler):
        self.db_handler = db_handler

    def collect_user_info(self, new_user=True):
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
                    if self.db_handler.find_user(user_info['email'].lower()):
                        print("This email address is already registered. Please log in instead.")
                        return self.collect_user_info(new_user=False)
                    break
                except EmailNotValidError as e:
                    print(str(e))
            
            password = input("Create a password:\n> ")
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
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
            rating = input("Please rate your experience with the chatbot (1 to 5):\n> ")
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
                print("Invalid input. Please enter a number between 1 and 5.")
                collect_rating()

        def collect_feedback():
            feedback = input("Please share your feedback about the chatbot:\n> ")
            feedback_data = {
                "user_id": user_id,
                "feedback": feedback
            }
            try:
                self.db_handler.insert_feedback(feedback_data)
                print("Thank you for your feedback! Your feedback can make our service better for the future.")
            except errors.PyMongoError as e:
                logging.error(f"Error collecting feedback: {e}")
                print("Sorry, there was an error collecting your feedback. Please try again later.")

        collect_rating()
        collect_feedback()


def main():
    db_handler = DatabaseHandler()
    logger = Logger()
    chatbot = Chatbot(api_key="b5f35af32c4170f17fc17b376e07f27f2639eca7ba1d77b9990eee6704042f08",
                      db_handler=db_handler, logger=logger)
    user_handler = UserHandler(db_handler)

    # Ask user if they have an account
    have_account = input("Do you have an account with Neetanshi? (yes/no)\n> ").strip().lower()
    if have_account == "yes":
        user_info = user_handler.collect_user_info(new_user=False)
    else:
        user_info = user_handler.collect_user_info(new_user=True)

    if not chatbot.session:
        chatbot.session.append({"role": "system", "content": f"You are Neetanshi, a friendly and knowledgeable mental health expert. Your role is to provide support, guidance, and coping strategies for various mental health challenges and situations that impact one's well-being. You are interacting with {user_info['name']}, a {user_info['age']}-year-old {user_info['sex']} from {user_info['country']} who works as a {user_info['occupation']}."})
        chatbot.session.append({"role": "assistant", "content": f"Hello {user_info['name']}! It's great to meet you. As your personal mental health expert, I'm here to listen and offer guidance whenever you need it. Whether you're struggling with anxiety, depression, or something else entirely, I'm here to support you."})

    print(f"Welcome to Neetanshi, {user_info['name']}! Your mental health chatbot.")
    print("Please select a scenario by entering the corresponding number or type your own scenario:")

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

    def display_options(options, allow_custom=False):
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
        if allow_custom:
            print(f"{len(options) + 1}. Enter your own scenario or problem")
        user_input = input("> ")
        if user_input.lower() in ['exit', 'quit', 'e', 'q']:
            print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
            user_handler.collect_rating_and_feedback(user_info['_id'])
            print("Goodbye! Take care.")
            exit()

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

    def handle_user_input(session, user_input, related_questions, user_info):
        if user_input.lower() in ['exit', 'quit', 'e', 'q']:
            print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
            user_handler.collect_rating_and_feedback(user_info['_id'])
            print("Goodbye! Take care.")
            return True

        if user_input in scenarios:
            chatbot.last_question = user_input  # Track the last question
            response = chatbot.generate_response(user_input, user_info)
            print("Neetanshi:", response)
            related_questions = scenarios[user_input]
        elif user_input in related_questions:
            chatbot.last_question = user_input  # Track the last question
            response = chatbot.generate_response(user_input, user_info)
            print("Neetanshi:", response)
            related_questions = related_questions[user_input]
        else:
            # Check if the input is related to a specific context
            if chatbot.last_question and chatbot.last_question in scenarios:
                response = chatbot.generate_response(user_input, user_info)
                print("Neetanshi:", response)
                related_questions = {}
            else:
                if not chatbot.is_mental_health_related(user_input):
                    response = "Sorry, I am here for mental health-related topics. Do you have any questions or issues related to mental health?"
                    print("Neetanshi:", response)
                    logger.log_interaction(user_input, response)
                else:
                    response = chatbot.generate_response(user_input, user_info)
                    print("Neetanshi:", response)
                    related_questions = {}

        while related_questions:
            print("\nHere are some related questions you might find helpful:")
            options = list(related_questions.keys())
            for i, option in enumerate(options, 1):
                print(f"{i}. {option}")
            print(f"{len(options) + 1}. Enter your own question or concern")
            next_input = input("> ")
            if next_input.lower() in ['exit', 'quit', 'e', 'q']:
                print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
                user_handler.collect_rating_and_feedback(user_info['_id'])
                print("Goodbye! Take care.")
                return True
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

        while True:
            next_input = input("Please provide more details or:\n1. Exit/Quit\n2. Ask another question\n3. Enter your own response\n> ")
            if next_input.lower() in ['exit', 'quit', 'e', 'q', '1']:
                print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
                user_handler.collect_rating_and_feedback(user_info['_id'])
                print("Goodbye! Take care.")
                return True
            elif next_input.lower() in ['2', 'ask another question']:
                print("Please select a scenario by entering the corresponding number or type your own scenario:")
                selected_scenario = display_options(initial_scenarios, allow_custom=True)
                return handle_user_input(session, selected_scenario, scenarios.get(selected_scenario, {}), user_info)
            elif next_input.lower() == '3':
                user_input = input("Please enter your own response:\n> ")
                response = chatbot.generate_response(user_input, user_info)
                print("Neetanshi:", response)
                return handle_user_input(session, user_input, related_questions, user_info)
            else:
                response = chatbot.generate_response(next_input, user_info)
                print("Neetanshi:", response)
                return handle_user_input(session, next_input, related_questions, user_info)

    initial_scenarios = list(scenarios.keys())
    selected_scenario = display_options(initial_scenarios, allow_custom=True)

    while selected_scenario and selected_scenario.lower() not in ["exit", "quit", "e", "q"]:
        should_exit = handle_user_input(chatbot.session, selected_scenario, scenarios.get(selected_scenario, {}), user_info)
        if should_exit:
            return

    print("Goodbye! Take care.")

if __name__ == "__main__":
    main()
