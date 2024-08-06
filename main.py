# initialize the telebot instance

import telebot
from telebot import types
import dotenv
import os
import requests
import json

import openai

dotenv.load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

client = openai.Client(
    api_key=os.getenv("DEEP_INFRA_API_KEY"),
    base_url="https://api.deepinfra.com/v1/openai",
)

context = {}


SYSTEM_PROMPT = """
You are a helpful tutor who gives concise explanations for ESL & English learners, give the best examples and explanations and connect with the students. 
STUDENTS ARE FROM CHINA and are learning English. Do not include Pinyin, but you can use Chinese characters if it helps.
OUTPUT IS IN JSON COMPATIBLE FORMAT, WITH THE SAME KEYS.
"""
# EXPLAIN IN ENGLISH, BUT TRY TO GUESS THE USER's NATIVE LANGUAGE and USE MINIMALLY AS FIT. YOU ARE ENCOURAGED TO ASK FOLLOW UPs TO UNDERSTAND THE STUDENT's NEEDS.

QUERY_PROMPT = """
AS A REFERENCE, EXPLANATIONS CAN INCLUDE, BUT NOT LIMITED TO: (this is just a reference)
- query_prediction: REQUIRED give out that specific phrase the user asks. STRING of the phrase, idiom, or word.
- definition: REQUIRED the meaning of the phrase
- examples: REQUIRED LIST OF STRINGS of different aspects where the query's phrase can be used.
- origin: OPTIONAL STRING that describes a story or a background of where that phrase came to be. What it originally meant and why it gets to used like this now.
- synonyms: OPTIONAL LIST OF STRINGS of similar words/phrases
- relate: OPTIONAL if this is a complicated idiom or phrase that only English native speakers understand, you use this to relate to others.
consider these aspects, but a lot of times you can't cover all of them depending on the query (ANSWER FOR REQUIRED FIELDS). These are just a reference to help you draft a great response.
FOR OPTIONAL, ONLY INCLUDE IF IT MAKES SENSE AND CAN RESONATE WITH THE USER BETTER.

DO YOUR BEST TO MAKE THE USER FEEL COMFORTABLE AND UNDERSTAND THE CONCEPT, THE CONCISE THE BETTER! YOU DON'T NEED TO ANSWER EVERYTHING.

USER's QUERY: {query}
REPOND IN ENGLISH, MUST BE JSON COMPATIBLE (NO COMMENTS) (LOADED STRAIGHT INTO A PYTHON DICT):
"""

# provide a helpful response in mostly English, but user's native language if it makes more sense and can resonate with the user better.


def ask_tutor(message, query, type="text"):
    if message.chat.id not in context:
        context[message.chat.id] = []
    history = []
    for item in context[message.chat.id]:
        history.append(
            {
                "role": "user",
                "content": item["query"],
            }
        )
        history.append(
            {
                "role": "assistant",
                "content": item["response"],
            }
        )

    response = (
        client.chat.completions.create(
            model="meta-llama/Meta-Llama-3.1-8B-Instruct",
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
            ]
            + history
            + [{"role": "user", "content": QUERY_PROMPT.format(query=query)}],
            max_tokens=350,
        )
        .choices[0]
        .message.content
    )

    # save this to our history
    context[message.chat.id].append(
        {"query": query, "response": response, "type": type}
    )
    with open("history.json", "w") as f:
        json.dump(context, f)
    
    try:
        response_json = json.loads(response)
        response = f"问题: {response_json['query_prediction']}\n\n定义: {response_json['definition']}\n\n例子: {"\n".join(response_json['examples'])}\n\n出处: {response_json.get('origin', 'N/A')}\n\n同义词: {", ".join(response_json.get('synonyms', ['N/A']))}\n\n关联: {response_json.get('relate', 'N/A')}"

        return response
    except Exception as e:
        return response


# when receiving the start and clear command
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Welcome to the bot! This bot will answer your English questions.",
    )
    context[message.chat.id] = []

    keyboard = types.ReplyKeyboardMarkup(row_width=1)
    add_button = types.KeyboardButton("New Task")
    clear_button = types.KeyboardButton("Clear Screen")
    keyboard.add(add_button, clear_button)


# when clicking the three buttons, add, view, and clear
@bot.message_handler(func=lambda message: message.text in ["New Task", "Clear Screen"])
def handle_buttons(message):
    if message.text == "New Task":
        # remove the history of the conversation
        context[message.chat.id] = []
    elif message.text == "Clear Screen":
        # clear everything on the screen except the buttons
        bot.send_message(
            message.chat.id,
            "Screen cleared.",
        )


# Handle if the message is an audio message
@bot.message_handler(content_types=["voice"])
def handle_audio(message):
    if message.from_user.is_bot:
        return

    try:
        # Step 1: Download the audio message
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        # Save the file temporarily
        with open("my_voice.mp3", "wb") as audio_file:
            audio_file.write(downloaded_file)

        # Inform the user that the message is being processed
        processing_message = bot.send_message(
            message.chat.id, "Processing your audio message..."
        )

        # Step 2: Send the audio to the DeepInfra API for transcription
        api_url = (
            "https://api.deepinfra.com/v1/inference/distil-whisper/distil-large-v3"
        )
        headers = {"Authorization": f'Bearer {os.getenv("DEEP_INFRA_API_KEY")}'}
        files = {"audio": open("my_voice.mp3", "rb")}
        response = requests.post(api_url, headers=headers, files=files)

        # Step 3: Parse the API response and extract the text
        if response.status_code == 200:
            response_json = response.json()
            text_segments = [segment["text"] for segment in response_json["segments"]]
            full_text = " ".join(text_segments)

            # Step 4: Call ask_tutor with the transcribed text
            tutor_response = ask_tutor(message, full_text, type="audio")

            # Edit the processing message with the result from ask_tutor
            bot.edit_message_text(
                tutor_response,
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
            )

        else:
            bot.edit_message_text(
                "Failed to process audio message. Please try again later.",
                chat_id=message.chat.id,
                message_id=processing_message.message_id,
            )

    except Exception as e:
        bot.edit_message_text(
            f"An error occurred: {str(e)}",
            chat_id=message.chat.id,
            message_id=processing_message.message_id,
        )


# handle if the message is photo message
@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    bot.send_message(
        message.chat.id,
        "Sorry, I can't process photo messages. Please send text messages.",
    )


# handle text message
@bot.message_handler(content_types=["text"])
def handle_text(message):
    # print the user id of message so we can limit
    # print(message)
    if message.from_user.is_bot:
        return

    processing_message = bot.send_message(
        message.chat.id,
        "Processing your text message...",
    )
    # edit the original message with the response from ask_tutor
    response = ask_tutor(message, message.text)
    bot.edit_message_text(
        response,
        chat_id=message.chat.id,
        message_id=processing_message.message_id,
    )


# start the bot
bot.polling()
