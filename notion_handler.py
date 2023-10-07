from notion_client import Client
import time
import threading
import re

# Thread-safe global cache for select options
select_option_cache = {}
lock = threading.Lock()

# Global dictionary to store existing chat IDs and their corresponding Notion URLs
chat_id_to_url = {}


def initialize_notion(token_v2, database_id):
    client = Client(auth=token_v2)
    db = client.databases.retrieve(database_id)

    start_cursor = None  # Initial cursor is None
    while True:
        # Perform the API call
        if start_cursor:
            results = client.databases.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100  # You can adjust the page size
            )
        else:
            results = client.databases.query(
                database_id=database_id,
                page_size=100  # You can adjust the page size
            )

        # Process the results
        for page in results["results"]:
            chat_id = page["properties"]["Chat ID"]["rich_text"][0]["text"]["content"]
            notion_url = page["url"]
            chat_id_to_url[chat_id] = notion_url

        # Check if there are more pages
        if "next_cursor" in results and results["next_cursor"]:
            start_cursor = results["next_cursor"]
        else:
            break

    return client, db, chat_id_to_url


def add_chat_to_notion(client, db, user_id, chat_id, summary, purpose, token_count, total_messages, subject_gen,
                       subject_spec, is_success, has_attachment, chat_log_content):
    global chat_id_to_url

    # Check if the chat ID already exists in Notion
    if chat_id in chat_id_to_url:
        print(f"Chat ID: {chat_id} already exists in Notion. Returning existing URL.")
        return chat_id_to_url[chat_id]

    user_id_option = get_or_create_select_option_cached(client, db, "User ID", user_id)
    subject_gen_option = get_or_create_select_option_cached(client, db, "Subject", subject_gen)

    new_page = {
        "Name": {"title": [{"text": {"content": f"{subject_spec}"}}]},
        "User ID": {"select": {"name": user_id_option["name"]}},
        "Chat ID": {"rich_text": [{"text": {"content": chat_id}}]},
        "Summary": {"rich_text": [{"text": {"content": summary}}]},
        "Purpose": {"rich_text": [{"text": {"content": purpose}}]},
        "Tokens": {"number": token_count},
        "Messages": {"number": total_messages},
        "Subject": {"select": {"name": subject_gen_option["name"]}},
        "Specific subject": {"rich_text": [{"text": {"content": subject_spec}}]},
        "Success?": {"checkbox": is_success},
        "Attachments?": {"checkbox": has_attachment},
    }
    max_retries = 3
    for retry_count in range(max_retries):
        try:
            created_page = client.pages.create(parent={"database_id": db["id"]}, properties=new_page)

            lines = [line.strip() for line in chat_log_content.split('\n') if line.strip()]
            children_blocks = generate_children_blocks(lines)

            for i in range(0, len(children_blocks), 100):
                chunk = children_blocks[i:i + 100]
                client.blocks.children.append(created_page["id"], children=chunk)

            print(f"Added chat log to Notion: {created_page.get('url')}")

            created_url = created_page.get("url")
            if created_url:
                chat_id_to_url[chat_id] = created_url

            return created_url

        except Exception as e:
            print(f"An error occurred: {e}")
            if retry_count < max_retries - 1:
                print("Retrying...")
                time.sleep(5)  # Add a delay of 5 seconds between retries
            else:
                print("Max retries reached. Skipping this chat log.")
                return None


def get_or_create_select_option_cached(client, db, property_name, option_name):
    global select_option_cache
    cache_key = f"{db['id']}_{property_name}"

    if cache_key not in select_option_cache:
        select_option_cache[cache_key] = {option["name"]: option for option in
                                          db["properties"][property_name]["select"]["options"]}

    if option_name in select_option_cache[cache_key]:
        return select_option_cache[cache_key][option_name]

    new_option = {
        "name": option_name,
        "color": "default",
    }
    db["properties"][property_name]["select"]["options"].append(new_option)
    updated_database = client.databases.update(db["id"], properties=db["properties"])
    select_option_cache[cache_key][option_name] = new_option

    return new_option


def generate_children_blocks(lines):
    children_blocks = []
    for line in lines:
        if line.startswith("User:") or line.startswith("AI:"):
            speaker, content = line.split(":", 1)
            children_blocks.append({"object": "block", "type": "heading_3",
                                    "heading_3": {"rich_text": [{"type": "text", "text": {"content": speaker}}]}})
            children_blocks.append({"object": "block", "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [{"type": "text", "text": {"content": content.strip()}}]}})
        elif re.match(r'^https://g0yu0l4pxj\.s3\.amazonaws\.com/appxxxx/.*\.(jpg|jpeg|png|gif|bmp|webp|tiff|ico|jfif)$',
                      line):
            # This line is an image URL from the specified domain
            children_blocks.append({"object": "block", "type": "image",
                                    "image": {"external": {"url": line}}})

        else:
            children_blocks.append({"object": "block", "type": "paragraph",
                                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
    return children_blocks
