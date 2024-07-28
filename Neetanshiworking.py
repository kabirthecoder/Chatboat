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

    def generate_response(self, user_input, user_info, prompt):
        self.session.append({"role": "user", "content": user_input})
        response = self.client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
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
            model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
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


scenarios = {
    "I am feeling very anxious lately.": {
        "visible": "I am feeling very anxious lately.",
        "prompt": "User is feeling very anxious lately",
        "sub_scenarios": {
            "Can you tell me more about what is making you feel anxious?": {
                "visible": "Can you tell me more about what is making you feel anxious?",
                "prompt": "User wants to share more about what is making them feel anxious",
                "sub_scenarios": {
                    "Is it related to work or personal life?": {
                        "visible": "Is it related to work or personal life?",
                        "prompt": "User's anxiety is related to work or personal life",
                        "sub_scenarios": {
                            "Work": {
                                "visible": "Work",
                                "prompt": "User's anxiety is related to work",
                                "sub_scenarios": {}
                            },
                            "Personal life": {
                                "visible": "Personal life",
                                "prompt": "User's anxiety is related to personal life",
                                "sub_scenarios": {}
                            }
                        }
                    },
                    "Do you experience physical symptoms as well?": {
                        "visible": "Do you experience physical symptoms as well?",
                        "prompt": "User experiences physical symptoms along with anxiety",
                        "sub_scenarios": {
                            "Yes": {
                                "visible": "Yes",
                                "prompt": "User experiences physical symptoms",
                                "sub_scenarios": {}
                            },
                            "No": {
                                "visible": "No",
                                "prompt": "User does not experience physical symptoms",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            },
            "How long have you been feeling this way?": {
                "visible": "How long have you been feeling this way?",
                "prompt": "User is asked how long they have been feeling this way",
                "sub_scenarios": {
                    "A few days": {
                        "visible": "A few days",
                        "prompt": "User has been feeling anxious for a few days",
                        "sub_scenarios": {}
                    },
                    "More than a week": {
                        "visible": "More than a week",
                        "prompt": "User has been feeling anxious for more than a week",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I am having trouble sleeping at night.": {
        "visible": "I am having trouble sleeping at night.",
        "prompt": "User is having trouble sleeping at night",
        "sub_scenarios": {
            "Have you noticed any patterns or habits that might be affecting your sleep?": {
                "visible": "Have you noticed any patterns or habits that might be affecting your sleep?",
                "prompt": "User is asked about patterns or habits affecting sleep",
                "sub_scenarios": {
                    "Caffeine intake": {
                        "visible": "Caffeine intake",
                        "prompt": "User's sleep trouble might be related to caffeine intake",
                        "sub_scenarios": {}
                    },
                    "Screen time before bed": {
                        "visible": "Screen time before bed",
                        "prompt": "User's sleep trouble might be related to screen time before bed",
                        "sub_scenarios": {}
                    }
                }
            },
            "Do you feel stressed or worried when you go to bed?": {
                "visible": "Do you feel stressed or worried when you go to bed?",
                "prompt": "User feels stressed or worried when going to bed",
                "sub_scenarios": {
                    "Yes, very stressed": {
                        "visible": "Yes, very stressed",
                        "prompt": "User feels very stressed when going to bed",
                        "sub_scenarios": {}
                    },
                    "No, just can't sleep": {
                        "visible": "No, just can't sleep",
                        "prompt": "User just can't sleep without feeling stressed",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I feel overwhelmed with my workload.": {
        "visible": "I feel overwhelmed with my workload.",
        "prompt": "User feels overwhelmed with their workload",
        "sub_scenarios": {
            "What tasks are causing you the most stress?": {
                "visible": "What tasks are causing you the most stress?",
                "prompt": "User is asked about tasks causing the most stress",
                "sub_scenarios": {
                    "High-priority tasks": {
                        "visible": "High-priority tasks",
                        "prompt": "High-priority tasks are causing the most stress for the user",
                        "sub_scenarios": {}
                    },
                    "Volume of tasks": {
                        "visible": "Volume of tasks",
                        "prompt": "The volume of tasks is causing the most stress for the user",
                        "sub_scenarios": {}
                    }
                }
            },
            "How do you currently manage your workload?": {
                "visible": "How do you currently manage your workload?",
                "prompt": "User is asked how they currently manage their workload",
                "sub_scenarios": {
                    "Prioritization": {
                        "visible": "Prioritization",
                        "prompt": "User manages workload by prioritization",
                        "sub_scenarios": {}
                    },
                    "Time management": {
                        "visible": "Time management",
                        "prompt": "User manages workload by time management",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I am experiencing relationship problems.": {
        "visible": "I am experiencing relationship problems.",
        "prompt": "User is experiencing relationship problems",
        "sub_scenarios": {
            "Can you describe the issues you are facing in your relationship?": {
                "visible": "Can you describe the issues you are facing in your relationship?",
                "prompt": "User is asked to describe the issues in their relationship",
                "sub_scenarios": {
                    "Communication issues": {
                        "visible": "Communication issues",
                        "prompt": "User is experiencing communication issues in their relationship",
                        "sub_scenarios": {}
                    },
                    "Trust issues": {
                        "visible": "Trust issues",
                        "prompt": "User is experiencing trust issues in their relationship",
                        "sub_scenarios": {}
                    }
                }
            },
            "How long have you been experiencing these problems?": {
                "visible": "How long have you been experiencing these problems?",
                "prompt": "User is asked how long they have been experiencing these problems",
                "sub_scenarios": {
                    "Recently": {
                        "visible": "Recently",
                        "prompt": "User has been experiencing relationship problems recently",
                        "sub_scenarios": {}
                    },
                    "For a long time": {
                        "visible": "For a long time",
                        "prompt": "User has been experiencing relationship problems for a long time",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I have been feeling very lonely and isolated.": {
        "visible": "I have been feeling very lonely and isolated.",
        "prompt": "User has been feeling very lonely and isolated",
        "sub_scenarios": {
            "Have you been able to connect with friends or family?": {
                "visible": "Have you been able to connect with friends or family?",
                "prompt": "User is asked if they have been able to connect with friends or family",
                "sub_scenarios": {
                    "Yes, but still feel lonely": {
                        "visible": "Yes, but still feel lonely",
                        "prompt": "User has connected with friends or family but still feels lonely",
                        "sub_scenarios": {}
                    },
                    "No, I haven't tried": {
                        "visible": "No, I haven't tried",
                        "prompt": "User hasn't tried to connect with friends or family",
                        "sub_scenarios": {}
                    }
                }
            },
            "What activities do you enjoy that might help you feel less isolated?": {
                "visible": "What activities do you enjoy that might help you feel less isolated?",
                "prompt": "User is asked about activities they enjoy that might help them feel less isolated",
                "sub_scenarios": {
                    "Hobbies": {
                        "visible": "Hobbies",
                        "prompt": "User enjoys hobbies that might help them feel less isolated",
                        "sub_scenarios": {}
                    },
                    "Social gatherings": {
                        "visible": "Social gatherings",
                        "prompt": "User enjoys social gatherings that might help them feel less isolated",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I am struggling with depression.": {
        "visible": "I am struggling with depression.",
        "prompt": "User is struggling with depression",
        "sub_scenarios": {
            "Have you been feeling down or hopeless?": {
                "visible": "Have you been feeling down or hopeless?",
                "prompt": "User is asked if they have been feeling down or hopeless",
                "sub_scenarios": {
                    "Yes": {
                        "visible": "Yes",
                        "prompt": "User has been feeling down or hopeless",
                        "sub_scenarios": {
                            "How long have you been feeling this way?": {
                                "visible": "How long have you been feeling this way?",
                                "prompt": "User is asked how long they have been feeling this way",
                                "sub_scenarios": {
                                    "A few days": {
                                        "visible": "A few days",
                                        "prompt": "User has been feeling down or hopeless for a few days",
                                        "sub_scenarios": {}
                                    },
                                    "More than two weeks": {
                                        "visible": "More than two weeks",
                                        "prompt": "User has been feeling down or hopeless for more than two weeks",
                                        "sub_scenarios": {}
                                    }
                                }
                            }
                        }
                    },
                    "No": {
                        "visible": "No",
                        "prompt": "User has not been feeling down or hopeless",
                        "sub_scenarios": {
                            "What specific thoughts or feelings are you experiencing?": {
                                "visible": "What specific thoughts or feelings are you experiencing?",
                                "prompt": "User is asked about specific thoughts or feelings they are experiencing",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            },
            "Are you having trouble enjoying activities you used to like?": {
                "visible": "Are you having trouble enjoying activities you used to like?",
                "prompt": "User is asked if they are having trouble enjoying activities they used to like",
                "sub_scenarios": {
                    "Yes": {
                        "visible": "Yes",
                        "prompt": "User is having trouble enjoying activities they used to like",
                        "sub_scenarios": {
                            "Can you tell me more about what has changed?": {
                                "visible": "Can you tell me more about what has changed?",
                                "prompt": "User is asked to share more about what has changed",
                                "sub_scenarios": {}
                            }
                        }
                    },
                    "No": {
                        "visible": "No",
                        "prompt": "User is not having trouble enjoying activities they used to like",
                        "sub_scenarios": {
                            "Have there been any other changes in your life recently?": {
                                "visible": "Have there been any other changes in your life recently?",
                                "prompt": "User is asked about other changes in their life recently",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            },
            "Do you find it hard to get out of bed or start your day?": {
                "visible": "Do you find it hard to get out of bed or start your day?",
                "prompt": "User is asked if they find it hard to get out of bed or start their day",
                "sub_scenarios": {
                    "Yes": {
                        "visible": "Yes",
                        "prompt": "User finds it hard to get out of bed or start their day",
                        "sub_scenarios": {
                            "What helps you to eventually get started?": {
                                "visible": "What helps you to eventually get started?",
                                "prompt": "User is asked what helps them to eventually get started",
                                "sub_scenarios": {}
                            }
                        }
                    },
                    "No": {
                        "visible": "No",
                        "prompt": "User does not find it hard to get out of bed or start their day",
                        "sub_scenarios": {
                            "What keeps you motivated?": {
                                "visible": "What keeps you motivated?",
                                "prompt": "User is asked what keeps them motivated",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            }
        }
    },
    "I am experiencing panic attacks.": {
        "visible": "I am experiencing panic attacks.",
        "prompt": "User is experiencing panic attacks",
        "sub_scenarios": {
            "Can you describe what happens during a panic attack?": {
                "visible": "Can you describe what happens during a panic attack?",
                "prompt": "User is asked to describe what happens during a panic attack",
                "sub_scenarios": {
                    "Physical symptoms": {
                        "visible": "Physical symptoms",
                        "prompt": "User experiences physical symptoms during a panic attack",
                        "sub_scenarios": {
                            "What physical symptoms do you experience?": {
                                "visible": "What physical symptoms do you experience?",
                                "prompt": "User is asked what physical symptoms they experience",
                                "sub_scenarios": {
                                    "Racing heart": {
                                        "visible": "Racing heart",
                                        "prompt": "User experiences racing heart during a panic attack",
                                        "sub_scenarios": {}
                                    },
                                    "Shortness of breath": {
                                        "visible": "Shortness of breath",
                                        "prompt": "User experiences shortness of breath during a panic attack",
                                        "sub_scenarios": {}
                                    }
                                }
                            }
                        }
                    },
                    "Emotional symptoms": {
                        "visible": "Emotional symptoms",
                        "prompt": "User experiences emotional symptoms during a panic attack",
                        "sub_scenarios": {
                            "What emotional symptoms do you experience?": {
                                "visible": "What emotional symptoms do you experience?",
                                "prompt": "User is asked what emotional symptoms they experience",
                                "sub_scenarios": {
                                    "Fear": {
                                        "visible": "Fear",
                                        "prompt": "User experiences fear during a panic attack",
                                        "sub_scenarios": {}
                                    },
                                    "Dread": {
                                        "visible": "Dread",
                                        "prompt": "User experiences dread during a panic attack",
                                        "sub_scenarios": {}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "How often do you experience panic attacks?": {
                "visible": "How often do you experience panic attacks?",
                "prompt": "User is asked how often they experience panic attacks",
                "sub_scenarios": {
                    "Daily": {
                        "visible": "Daily",
                        "prompt": "User experiences panic attacks daily",
                        "sub_scenarios": {}
                    },
                    "Weekly": {
                        "visible": "Weekly",
                        "prompt": "User experiences panic attacks weekly",
                        "sub_scenarios": {}
                    },
                    "Occasionally": {
                        "visible": "Occasionally",
                        "prompt": "User experiences panic attacks occasionally",
                        "sub_scenarios": {}
                    }
                }
            },
            "What coping strategies have you tried?": {
                "visible": "What coping strategies have you tried?",
                "prompt": "User is asked what coping strategies they have tried",
                "sub_scenarios": {
                    "Breathing exercises": {
                        "visible": "Breathing exercises",
                        "prompt": "User has tried breathing exercises to cope with panic attacks",
                        "sub_scenarios": {}
                    },
                    "Grounding techniques": {
                        "visible": "Grounding techniques",
                        "prompt": "User has tried grounding techniques to cope with panic attacks",
                        "sub_scenarios": {}
                    },
                    "None": {
                        "visible": "None",
                        "prompt": "User has not tried any coping strategies for panic attacks",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I have been feeling very sad recently.": {
        "visible": "I have been feeling very sad recently.",
        "prompt": "User has been feeling very sad recently",
        "sub_scenarios": {
            "Do you know what is making you feel sad?": {
                "visible": "Do you know what is making you feel sad?",
                "prompt": "User is asked if they know what is making them feel sad",
                "sub_scenarios": {
                    "Yes": {
                        "visible": "Yes",
                        "prompt": "User knows what is making them feel sad",
                        "sub_scenarios": {
                            "Can you share more about what is causing these feelings?": {
                                "visible": "Can you share more about what is causing these feelings?",
                                "prompt": "User is asked to share more about what is causing these feelings",
                                "sub_scenarios": {}
                            }
                        }
                    },
                    "No": {
                        "visible": "No",
                        "prompt": "User does not know what is making them feel sad",
                        "sub_scenarios": {
                            "Is there a particular time of day or activity that triggers your sadness?": {
                                "visible": "Is there a particular time of day or activity that triggers your sadness?",
                                "prompt": "User is asked if there is a particular time of day or activity that triggers their sadness",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            },
            "How long have you been feeling this way?": {
                "visible": "How long have you been feeling this way?",
                "prompt": "User is asked how long they have been feeling this way",
                "sub_scenarios": {
                    "A few days": {
                        "visible": "A few days",
                        "prompt": "User has been feeling sad for a few days",
                        "sub_scenarios": {}
                    },
                    "Several weeks": {
                        "visible": "Several weeks",
                        "prompt": "User has been feeling sad for several weeks",
                        "sub_scenarios": {}
                    },
                    "Months": {
                        "visible": "Months",
                        "prompt": "User has been feeling sad for months",
                        "sub_scenarios": {}
                    }
                }
            },
            "Have you talked to anyone about how you're feeling?": {
                "visible": "Have you talked to anyone about how you're feeling?",
                "prompt": "User is asked if they have talked to anyone about how they are feeling",
                "sub_scenarios": {
                    "Yes": {
                        "visible": "Yes",
                        "prompt": "User has talked to someone about how they are feeling",
                        "sub_scenarios": {
                            "Who did you talk to and how did it go?": {
                                "visible": "Who did you talk to and how did it go?",
                                "prompt": "User is asked who they talked to and how it went",
                                "sub_scenarios": {}
                            }
                        }
                    },
                    "No": {
                        "visible": "No",
                        "prompt": "User has not talked to anyone about how they are feeling",
                        "sub_scenarios": {
                            "Is there someone you feel comfortable talking to?": {
                                "visible": "Is there someone you feel comfortable talking to?",
                                "prompt": "User is asked if there is someone they feel comfortable talking to",
                                "sub_scenarios": {}
                            }
                        }
                    }
                }
            }
        }
    },
    "I feel like I'm not good enough.": {
        "visible": "I feel like I'm not good enough.",
        "prompt": "User feels like they are not good enough",
        "sub_scenarios": {
            "What makes you feel this way?": {
                "visible": "What makes you feel this way?",
                "prompt": "User is asked what makes them feel this way",
                "sub_scenarios": {
                    "Work": {
                        "visible": "Work",
                        "prompt": "User feels not good enough due to work",
                        "sub_scenarios": {}
                    },
                    "Relationships": {
                        "visible": "Relationships",
                        "prompt": "User feels not good enough due to relationships",
                        "sub_scenarios": {}
                    },
                    "Personal expectations": {
                        "visible": "Personal expectations",
                        "prompt": "User feels not good enough due to personal expectations",
                        "sub_scenarios": {}
                    }
                }
            },
            "How do you usually deal with these feelings?": {
                "visible": "How do you usually deal with these feelings?",
                "prompt": "User is asked how they usually deal with these feelings",
                "sub_scenarios": {
                    "Talking to friends": {
                        "visible": "Talking to friends",
                        "prompt": "User deals with these feelings by talking to friends",
                        "sub_scenarios": {}
                    },
                    "Journaling": {
                        "visible": "Journaling",
                        "prompt": "User deals with these feelings by journaling",
                        "sub_scenarios": {}
                    },
                    "Keeping it to myself": {
                        "visible": "Keeping it to myself",
                        "prompt": "User deals with these feelings by keeping it to themselves",
                        "sub_scenarios": {}
                    }
                }
            },
            "What do you do to take care of yourself?": {
                "visible": "What do you do to take care of yourself?",
                "prompt": "User is asked what they do to take care of themselves",
                "sub_scenarios": {
                    "Exercise": {
                        "visible": "Exercise",
                        "prompt": "User takes care of themselves by exercising",
                        "sub_scenarios": {}
                    },
                    "Hobbies": {
                        "visible": "Hobbies",
                        "prompt": "User takes care of themselves through hobbies",
                        "sub_scenarios": {}
                    },
                    "Relaxation techniques": {
                        "visible": "Relaxation techniques",
                        "prompt": "User takes care of themselves using relaxation techniques",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    },
    "I am dealing with grief and loss.": {
        "visible": "I am dealing with grief and loss.",
        "prompt": "User is dealing with grief and loss",
        "sub_scenarios": {
            "Who or what have you lost?": {
                "visible": "Who or what have you lost?",
                "prompt": "User is asked who or what they have lost",
                "sub_scenarios": {
                    "Loved one": {
                        "visible": "Loved one",
                        "prompt": "User has lost a loved one",
                        "sub_scenarios": {}
                    },
                    "Pet": {
                        "visible": "Pet",
                        "prompt": "User has lost a pet",
                        "sub_scenarios": {}
                    },
                    "Job or opportunity": {
                        "visible": "Job or opportunity",
                        "prompt": "User has lost a job or opportunity",
                        "sub_scenarios": {}
                    }
                }
            },
            "How have you been coping with your loss?": {
                "visible": "How have you been coping with your loss?",
                "prompt": "User is asked how they have been coping with their loss",
                "sub_scenarios": {
                    "Talking to family or friends": {
                        "visible": "Talking to family or friends",
                        "prompt": "User has been coping by talking to family or friends",
                        "sub_scenarios": {}
                    },
                    "Professional counseling": {
                        "visible": "Professional counseling",
                        "prompt": "User has been coping through professional counseling",
                        "sub_scenarios": {}
                    },
                    "Trying to stay busy": {
                        "visible": "Trying to stay busy",
                        "prompt": "User has been coping by trying to stay busy",
                        "sub_scenarios": {}
                    }
                }
            },
            "How long has it been since your loss?": {
                "visible": "How long has it been since your loss?",
                "prompt": "User is asked how long it has been since their loss",
                "sub_scenarios": {
                    "A few days": {
                        "visible": "A few days",
                        "prompt": "It has been a few days since user's loss",
                        "sub_scenarios": {}
                    },
                    "Weeks": {
                        "visible": "Weeks",
                        "prompt": "It has been weeks since user's loss",
                        "sub_scenarios": {}
                    },
                    "Months": {
                        "visible": "Months",
                        "prompt": "It has been months since user's loss",
                        "sub_scenarios": {}
                    },
                    "Years": {
                        "visible": "Years",
                        "prompt": "It has been years since user's loss",
                        "sub_scenarios": {}
                    }
                }
            }
        }
    }
}

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

    def display_options(options, allow_custom=False):
        for i, option in enumerate(options, 1):
            print(f"{i}. {option}")
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
            else:
                print("Invalid selection. Please enter a number corresponding to an option.")
                return None
        except ValueError:
            return user_input

    def handle_user_input(session, user_input, related_questions, user_info, prompt=None):
        if user_input.lower() in ['exit', 'quit', 'e', 'q']:
            print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
            user_handler.collect_rating_and_feedback(user_info['_id'])
            print("Goodbye! Take care.")
            return True

        if user_input in scenarios:
            chatbot.last_question = user_input  # Track the last question
            response = chatbot.generate_response(user_input, user_info, prompt)
            print("Neetanshi:", response)
            related_questions = scenarios[user_input]['sub_scenarios']
        elif user_input in related_questions:
            chatbot.last_question = user_input  # Track the last question
            response = chatbot.generate_response(user_input, user_info, prompt)
            print("Neetanshi:", response)
            related_questions = related_questions[user_input]['sub_scenarios']
        else:
            if chatbot.last_question and chatbot.last_question in scenarios:
                response = chatbot.generate_response(user_input, user_info, prompt)
                print("Neetanshi:", response)
                related_questions = {}
            else:
                if not chatbot.is_mental_health_related(user_input):
                    response = "Sorry, I am here for mental health-related topics. Do you have any questions or issues related to mental health?"
                    print("Neetanshi:", response)
                    logger.log_interaction(user_input, response)
                else:
                    response = chatbot.generate_response(user_input, user_info, prompt)
                    print("Neetanshi:", response)
                    related_questions = {}

        while related_questions:
            print("\nHere are some related questions you might find helpful:")
            options = list(related_questions.keys())
            for i, option in enumerate(options, 1):
                print(f"{i}. {option}")
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
                    return handle_user_input(session, selected_question, related_questions[selected_question], user_info, related_questions[selected_question]['prompt'])
                else:
                    return handle_user_input(session, next_input, {}, user_info)
            except ValueError:
                return handle_user_input(session, next_input, {}, user_info)

        while True:
            next_input = input("Please provide more details or type 'exit' to quit:\n> ")
            if next_input.lower() in ['exit', 'quit', 'e', 'q']:
                print("Thank you for using Neetanshi. Before you go, we would appreciate your feedback to help us improve.")
                user_handler.collect_rating_and_feedback(user_info['_id'])
                print("Goodbye! Take care.")
                return True
            response = chatbot.generate_response(next_input, user_info, prompt)
            print("Neetanshi:", response)
            return handle_user_input(session, next_input, related_questions, user_info, prompt)

    initial_scenarios = list(scenarios.keys())
    selected_scenario = display_options(initial_scenarios, allow_custom=True)

    while selected_scenario and selected_scenario.lower() not in ["exit", "quit", "e", "q"]:
        should_exit = handle_user_input(chatbot.session, selected_scenario, scenarios.get(selected_scenario, {}).get('sub_scenarios', {}), user_info, scenarios.get(selected_scenario, {}).get('prompt', None))
        if should_exit:
            return

    print("Goodbye! Take care.")

if __name__ == "__main__":
    main()
