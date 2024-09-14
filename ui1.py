import asyncio
import streamlit as st
import logging  # Import the logging module
from chatbot import Chatbot, DatabaseHandler, Logger, UserHandler
import bcrypt
from pymongo import errors
import json
from email_validator import validate_email, EmailNotValidError

# Load scenarios from JSON file
def load_scenarios():
    with open('scenarios.json') as f:
        return json.load(f)["scenarios"]

# Initialize components
db_handler = DatabaseHandler()
logger = Logger()
scenarios = load_scenarios()

# Initialize the Chatbot without 'scenarios' argument
chatbot = Chatbot(api_key="6abe6cd1c19a11f9919847e8deae4040d04701b7c1916eabc06d855fdfaff639",
                  db_handler=db_handler, logger=logger)

# Assign scenarios after initialization
chatbot.scenarios = scenarios

user_handler = UserHandler(db_handler)

# Initialize session state
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'scenario_path' not in st.session_state:
    st.session_state.scenario_path = []
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'last_response' not in st.session_state:
    st.session_state.last_response = ""
if 'current_scenarios' not in st.session_state:
    st.session_state.current_scenarios = scenarios
if 'conversation_context' not in st.session_state:
    st.session_state.conversation_context = []

# Asynchronous function to get chatbot response
async def get_chatbot_response(chatbot, input_text, user_info):
    try:
        # Direct call since generate_response might not be async
        print(user_info)
        response = chatbot.generate_response(input_text, user_info)
        return response
    except Exception as e:
        return f"Error in generating response: {e}"

def login_or_register():
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    action = st.radio("Action", ["Login", "Register"])

    if action == "Register":
        name = st.text_input("Name")
        occupation = st.text_input("Occupation")
        age = st.text_input("Age")
        sex = st.selectbox("Sex", ["male", "female", "other"])
        country = st.text_input("Country")

    if st.button("Submit"):        
         if action == "Login":
            try:
             user_info = db_handler.find_user(email.lower())
             if user_info:
                logging.info("User found in database.")
                logging.info(f"Retrieved password: {user_info['password']}")
                if bcrypt.checkpw(password.encode('utf-8'), user_info['password']):
                    st.session_state.user_info = user_info
                    st.success(f"Welcome back, {user_info['name']}!")
                    initialize_chatbot_session(user_info)
                    load_previous_session(user_info)
                else:
                    logging.error("Password mismatch.")
                    st.error("Invalid email or password.")
             else:
                st.error("User not found.")
            except Exception as e:
                st.error(f"An error occurred during login: {str(e)}")
                logging.error(f"Login error: {str(e)}")   
    else:
        try:
                # Validate email
                v = validate_email(email)
                validated_email = v.email.lower()

                # Check if the email is already registered
                if db_handler.find_user(validated_email):
                    st.error(
                        "This email address is already registered. Please log in instead.")
                    return

                # Proceed with registration
                hashed_password = bcrypt.hashpw(
                    password.encode('utf-8'), bcrypt.gensalt())

                user_info = {
                    "email": validated_email,
                    "password": hashed_password,  # Store as bytes
                    "name": name,
                    "occupation": occupation,
                    "age": age,
                    "sex": sex,
                    "country": country
                }

                db_handler.insert_user(user_info)
                st.session_state.user_info = user_info
                st.success("Registration successful!")
                initialize_chatbot_session(user_info)

        except EmailNotValidError as e:
                st.error(f"Invalid email: {str(e)}")
        except errors.DuplicateKeyError:
                st.error(
                    "This email address is already registered. Please log in instead.")

def initialize_chatbot_session(user_info):
    chatbot.initialize_session(user_info)
    st.session_state.current_scenarios = chatbot.scenarios

def load_previous_session(user_info):
    interactions = db_handler.get_interactions(user_info['_id'])
    for interaction in reversed(interactions):
        st.session_state.chat_history.insert(
            0, (interaction['user_input'], interaction['bot_response']))
    if interactions:
        last_interaction = interactions[-1]
        st.session_state.last_response = last_interaction['bot_response']

def display_chat_history():
    with st.sidebar:
        if st.button("New Chat"):
            st.session_state.scenario_path = []
            st.session_state.chat_history = []
            st.session_state.last_response = ""
            st.session_state.conversation_context = []
            st.rerun()  # Updated the deprecated call
        st.write("Your History")
        interactions = db_handler.get_interactions(
            st.session_state.user_info['_id'])
        for i, interaction in enumerate(reversed(interactions)):
            if st.button(f"Interaction {i+1}"):
                st.session_state.chat_history = [
                    (interaction['user_input'], interaction['bot_response'])]

def display_dynamic_scenarios(scenarios, path):
    current_level = scenarios
    for step in path:
        if "sub_scenarios" in current_level[step]:
            current_level = current_level[step]["sub_scenarios"]
        elif "nested_sub_scenarios" in current_level[step]:
            current_level = current_level[step]["nested_sub_scenarios"]
        elif "further_nested_sub_scenarios" in current_level[step]:
            current_level = current_level[step]["further_nested_sub_scenarios"]
        elif "deeply_nested_sub_scenarios" in current_level[step]:
            current_level = current_level[step]["deeply_nested_sub_scenarios"]
        else:
            current_level = {}

    options = [(key, value['visible']) for key, value in current_level.items()]
    if options:
        option_dict = {label: key for key, label in options}
        selected_label = st.selectbox("Select an option:", [
                                      ""] + list(option_dict.keys()), key=f"dynamic_dropdown_{len(path)}")

        if selected_label and selected_label != "":
            new_path = path + [option_dict[selected_label]]
            st.session_state.scenario_path = new_path
            display_dynamic_scenarios(scenarios, new_path)
    else:
        st.write("No further scenarios available.")
        st.rerun()  # Updated the deprecated call

def main_interface():
    st.write(f"Welcome back, {st.session_state.user_info['name']}!")

    st.write("Chat History")
    for user_input, response in st.session_state.chat_history:
        st.markdown(
            f"<div style='text-align: right;'>You: {user_input}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='text-align: left;'>Neetanshi: {response}</div>", unsafe_allow_html=True)

    if st.session_state.last_response:
        st.write(f"Neetanshi: {st.session_state.last_response}")

    st.write("Choose a scenario:")
    display_dynamic_scenarios(
        st.session_state.current_scenarios, st.session_state.scenario_path)

    custom_input = st.text_area("Your Input (optional)", height=100)

    # Modify the Submit Input button to use async response generation
    if st.button("Submit Input"):
        scenario_text = ' -> '.join(
            st.session_state.scenario_path) if st.session_state.scenario_path else ""
        input_text = f"{scenario_text}. {custom_input}".strip(
        ) if custom_input else scenario_text

        st.session_state.conversation_context.append(
            {"role": "user", "content": input_text})

        # Use asyncio to run the chatbot response asynchronously
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(get_chatbot_response(
                chatbot, input_text, st.session_state.user_info))

            if response:
                st.session_state.conversation_context.append(
                    {"role": "assistant", "content": response})
                st.session_state.chat_history.insert(
                    0, (input_text, response))  # Add latest at the top
                st.session_state.last_response = response

                db_handler.update_interactions(st.session_state.user_info['_id'], {
                                               "user_input": input_text, "bot_response": response})

                st.rerun()  # Updated the deprecated call
            else:
                st.error("Failed to generate a response. Please try again.")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

def main():
    st.title("Neetanshi - Mental Health Chatbot")

    if st.session_state.user_info is None:
        login_or_register()
    else:
        display_chat_history()
        main_interface()

if __name__ == "__main__":
    main()
