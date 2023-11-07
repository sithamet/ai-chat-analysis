import pandas as pd
from ai_requests import make_ai_request, log_token_usage
from notion_handler import initialize_notion, add_chat_to_notion
import itertools
import tiktoken
import json
from dotenv import load_dotenv
import os
import time

load_dotenv()

test_mode = False  # Set to True to run the script in test mode, processing only 10 first chats

# Initialize Notion database
client, db, chat_ids_to_notion_urls = initialize_notion(
    token_v2=os.getenv("NOTION_API_KEY"),
    database_id=os.getenv("NOTION_DB_ID")
)


def count_tokens(text):
    encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = len(encoding.encode(text))

    return num_tokens


# Function for progress bar
def progress_bar(iteration, total, bar_length=50):
    percent = float(iteration) / float(total)
    arrow = '=' * int(round(percent * bar_length) - 1)
    spaces = ' ' * (bar_length - len(arrow))

    cat_cycle = itertools.cycle(['(^・o・^)ﾉ”', '(^・w・^)ﾉ”', '(^・o・^)ﾉ”', '(^・w・^)ﾉ”'])
    cat = next(cat_cycle)

    print(f'\rProgress: [{arrow + spaces}] {int(percent * 100)}%  {cat}', end='')


print("Stage 1: Loading and Sorting CSV")
# Load the original CSV into a DataFrame and sort it
file_path = 'input/chats.csv'
df = pd.read_csv(file_path)
df_sorted = df.sort_values(by=['chat_id', 'prompt_created_at'])
total_rows = len(df_sorted)
print(f"Total rows to process: {total_rows}")

# Initialize an empty dictionary to store the chat logs mapped to user_id and chat_id
user_chat_logs = {}
message_count = {}

print("Stage 2: Building Chat Logs")
chat_has_attachment = {}


unique_users = df_sorted['user_id'].nunique()
print(f"Total unique users: {unique_users}")
# Iterate through the sorted DataFrame to build the chat logs
for index, row in df_sorted.iterrows():
    user_id = row['user_id']
    chat_id = row['chat_id']
    user_prompt = row['user_prompt']
    ai_response = row['ai_response']
    prompt_attachment = row['prompt_attachment']  # Get the prompt_attachment

    if user_id not in user_chat_logs:
        user_chat_logs[user_id] = {}
        message_count[user_id] = {}
    if chat_id not in user_chat_logs[user_id]:
        user_chat_logs[user_id][chat_id] = []
        message_count[user_id][chat_id] = 0

    if pd.notna(prompt_attachment):
        # print(f"Chat ID: {chat_id} has an attachment. {prompt_attachment}")
        user_chat_logs[user_id][chat_id].append(f"User: {user_prompt}\n{prompt_attachment}\nAI: {ai_response}\n")

        if chat_id not in chat_has_attachment:
            chat_has_attachment[chat_id] = True  # Mark that this chat has an attachment
    else:
        user_chat_logs[user_id][chat_id].append(f"User: {user_prompt}\nAI: {ai_response}\n")

    message_count[user_id][chat_id] += 1  # Incrementing the message count for the chat_id
    progress_bar(index + 1, len(df_sorted))

print("\nStage 3: Combining Chat Entries")

# Announce number of unique chats
unique_chats = sum(len(chats) for chats in user_chat_logs.values())
print(f"Total unique chats: {unique_chats}")

# Combine the chat entries for each 'chat_id' into a single string
for index, (user_id, chat_dict) in enumerate(user_chat_logs.items()):
    for chat_id, entries in chat_dict.items():
        user_chat_logs[user_id][chat_id] = "\n".join(entries)
    progress_bar(index + 1, len(user_chat_logs))

print("\nStage 4: Making API Requests and Storing Results")
stage_4_start_time = time.time()

# Initialize an empty list to store the results
results = []

# Loop through each user and their chat logs
total_chats = sum(len(chats) for chats in user_chat_logs.values())
completed_chats = 0
if test_mode:
    print("Test mode is enabled. Will process only 10 chats.")
    total_chats = 10
else:
    total_chats = sum(len(chats) for chats in user_chat_logs.values())

print(f"Total chats to process: {total_chats}")

total_chats_processed = 0  # Initialize a counter to keep track of total chats processed

instructions = """
You are a knowledgeable subject expert assisting with chat logs analysis. The user will provide you with the chat logs, and you will analyze them to find the next parameters.

##Summary

Generate progressively concise, entity-rich summaries of user chat logs in 5 iterations. Focus on what the User was 
doing, what  responses they got, and if they were correct. Each iteration must identify 1-3 new, relevant, specific, 
and faithful entities from the chat, and integrate them into a rewritten summary without increasing word count. The 
first summary should be about 80 words and intentionally vague. Subsequent summaries must maintain all prior 
entities, optimizing for brevity and clarity. Do include only the final summary. Start it with what the user wanted.

##Purpose

Identify the purpose of the user chatting with the assistant. What did they want to achieve?

##Specific subject

Identify the academic subject of this chat log. 

##General subject

Select the one and only one most-suiting subject of this chat log from the list: Economics, Finance, Accounting and Banking, 
Chemistry, English, Statistics, Engineering, Maths, Physics, Computer Science, Philosophy, IT (coding), Culture, 
Business and Management, Marketing and PR, Law and International Law, Other, Religion, History and Anthropology, 
Biology and Life Sciences, Environmental Science, Psychology, Education, Linguistics, Healthcare and Nursing, 
Political Science, Sociology, Art, Literature, Music, Design and Architecture, HRM.

Avoid using "Other" if possible. Try to deduce: e.g. if the chat is about a book, it's literature, and if it's about 
a country, it's History and Anthropology.

##Success

Evaluate the purpose of the chat and the outcomes. Did the user succeed in achieving their purpose?

In response to a student's question, you must answer with a pseudo-JSON formatted response with ALL parameters from 
the list below, where boolean is either true or false depending on the question type and its requirements:

summary: "string" — summary. It MUST start with "The user wanted to..." 

purpose: "string" — purpose

subject_spec: "string" — specific subject

subject_gen: "string" — general subject, one and only one 

success: boolean — is success

E.g. 
{
    "summary": "string",
    "purpose": "string",
    "subject_spec": "string",
    "subject_gen": "string",
    "success": boolean
}

Format all parameters you choose as a pseudo-JSON array. Reply only with that array.
"""

recheck_instructions = "You are a helpful AI assistant."
prompt = f"""
Here's the JSON response from the API. 

It must follow the format below. Please check if it does. If it doesn't, please correct it. If it does, 
please copy-n-paste it. Only reply with the JSON response.

{{
"summary": "string",
    "purpose": "string",
    "subject_spec": "string",
    "subject_gen": "string",
    "success": boolean
}}

"""

for user_id, chat_dict in user_chat_logs.items():
    chat_count = 0
    for chat_id, chat_log in chat_dict.items():
        if chat_id in chat_ids_to_notion_urls:
            print(f"ChatID {chat_id} already exists in Notion. Skipping...")
            continue

        if test_mode and total_chats_processed >= 10:
            break

        token_count = count_tokens(chat_log)
        if token_count > 12000:
            truncated_chat_log = chat_log
            while token_count > 12000:
                truncated_chat_log = truncated_chat_log[:-1000]
                token_count = count_tokens(truncated_chat_log)
        else:
            truncated_chat_log = chat_log

        max_retries = 3  # Number of times to retry

        for retry_count in range(max_retries):
            try:
                # Make API request
                analysis = make_ai_request(
                    system_prompt=instructions,
                    user_input=truncated_chat_log,
                    user_prompt="Analyze this chat log. Return only one final response. Do not include any other "
                                "text. Your response must be exactly one JSON object."
                )

                print(f"\n {analysis} \n")

                # Validate and check the JSON structure
                # checked = make_ai_request(
                #     system_prompt=recheck_instructions,
                #     user_input=prompt,
                #     user_prompt=analysis
                # )

                # Pre-process to remove array brackets if necessary
                if analysis.startswith('[') and analysis.endswith(']'):
                    analysis = analysis[1:-1].strip()

                # Try to parse the JSON
                data = json.loads(analysis, object_hook=dict)

                # Validate the schema of the JSON
                required_keys = ["summary", "purpose", "subject_spec", "subject_gen", "success"]
                if all(key in data for key in required_keys):
                    summary = data.get("summary", "N/A")
                    purpose = data.get("purpose", "N/A")
                    subject_spec = data.get("subject_spec", "N/A")
                    subject_gen = data.get("subject_gen", "N/A")
                    success = data.get("success", False)
                    has_attachment = chat_has_attachment.get(chat_id, False)  # Get the attachment flag for this chat

                    total_messages = message_count[user_id][chat_id] * 2
                    print(
                        f"\nUser ID: {user_id}, Chat ID: {chat_id}, Total Messages: {total_messages}, Token Count: {token_count}")

                    results.append({
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "summary": summary,
                        "purpose": purpose,
                        "subject_spec": subject_spec,
                        "subject_gen": subject_gen,
                        "is_success": success,
                        "token_count": token_count,
                        "total_messages": total_messages,
                        "has_attachment": has_attachment,
                        "log": add_chat_to_notion(client, db, user_id, chat_id, summary, purpose, token_count,
                                                  total_messages, subject_gen, subject_spec, success, has_attachment, chat_log)
                    })

                    break  # Successfully parsed and validated JSON, break out of retry loop
                else:
                    raise ValueError("JSON does not match the required schema.")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"An error occurred: {e}")
                print("Retrying...")
                if retry_count == max_retries - 1:
                    print("Max retries reached. Skipping this chat log.")
                continue  # Retry the API request and JSON parsing

        chat_count += 1
        completed_chats += 1
        total_chats_processed += 1
        progress_bar(completed_chats, total_chats)
    if test_mode and total_chats_processed >= 10:
        break  # Break out of outer loop if in test mode and 10 chats have been processed

stage_4_end_time = time.time()
stage_4_elapsed_time = stage_4_end_time - stage_4_start_time
print(f"Stage 4 completed in {stage_4_elapsed_time:.2f} seconds")

print("\nStage 5: Saving to CSV")
# Convert the results to a DataFrame and save to CSV
result_df = pd.DataFrame(results)
result_df.to_csv("Chat_Analysis.csv", index=False)

print("Stage 6: Logging Token Usage")
# Log token usage
log_token_usage()
