# ai-chat-analysis

## Chat Log Analysis 

This Python script loads CSV chat log data, processes it, combines chat entries, forwards each chat to an AI for analysis, records response and finally outputs results to a CSV file.

The AI performs a summary, purpose of user chatting, general and specific subject of the chat and whether the purpose of the chat was achieved.

## Prerequisites 

- Python 3.11.5
- pandas
- tiktoken
- json
- dotenv
- os
- time

It also looks like this script is using an external AI service (as seen in the function `make_ai_request`) as well as handles requests from Notion API.

You must have a `.env` file with the necessary environment variables (Notion API Key, Notion Database ID), and your chat log data must reside in a CSV file named `chats.csv` at the location of the script.

## How to run

To run this script, do the following: 
- Put chat's import to input/chats.csv 

Then, use the following command in terminal:

```
python main.py
```

## What this script does
1. It loads environment variables from a .env file to initialize Notion API.
2. It loads a CSV file named chats.csv and sorts the data according to the chat_id and prompt_created_at fields.
3. For each unique chat, it combines the chat entries into a single string.
4. Using an AI and Notion API, the script requests an analysis of each chat and validates, checks the JSON structure of the response, then stores the response in a result list.
5. If the AI response is as expected, the chat, along with other metrics is logged in Notion and added to results. This process repeats for all chats in the provided CSV file.
6. The result list is then converted into a pandas DataFrame and saved to CSV.

Token usage is also logged.
Note: There's a test mode which, when enabled, processes only the first 10 chat logs.

---

Please respect the ethics of software usage and do not use this software for any malicious purposes. The author of this software does not assume any responsibilty for misuse of this software.
