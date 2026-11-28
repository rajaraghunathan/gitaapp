import re, time, unicodedata, os, uuid, requests, json
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from deep_translator import GoogleTranslator

from dotenv import load_dotenv
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

def remove_non_printable_from_object(any_obj):
    strings_to_clean = []
    def collect_strings(data):
        if isinstance(data, dict):
            for v in data.values(): collect_strings(v)
        elif isinstance(data, list):
            for item in data: collect_strings(item)
        elif isinstance(data, str):
            strings_to_clean.append(data)

    collect_strings(any_obj)

    cleaned_strings = []
    for string in strings_to_clean:
        cleaned_string = remove_non_printable(string)
        cleaned_strings.append(cleaned_string)

    string_iterator = iter(cleaned_strings)

    def rebuild_nested(data):
        if isinstance(data, dict):
            return {k: rebuild_nested(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [rebuild_nested(item) for item in data]
        elif isinstance(data, str):
            return next(string_iterator, data)
        return data

    cleaned_data = rebuild_nested(any_obj)
    return cleaned_data

def remove_non_printable(dirty_text):
    """
    Filters out characters belonging to Unicode control 'C' categories:
    Cc (Control), Cf (Format - includes \u200c), Cs (Surrogate), Co (Private Use), Cn (Unassigned)
    while safely preserving normal text whitespace like spaces, tabs, and newlines.
    """
    if not dirty_text or not isinstance(dirty_text, str):
        return dirty_text
    normalized_text = unicodedata.normalize("NFC", dirty_text)
    cleaned_text = "".join(
        ch for ch in normalized_text
        if not unicodedata.category(ch).startswith('C')
        or ch in ('\n', '\r', '\t')  # Explicitly preserve standard structural layout whitespace
    )
    return cleaned_text

def batch_translate_google(data_list, source_langauge='en', target_language='en'):
    try:
        if len(data_list) == 0 or not isinstance(data_list, list) :
            return [], True
        translator = GoogleTranslator(source=source_langauge, target=target_language)
        value_list = [data.get('en', '').strip() for data in data_list]

        joined_list = ' ||| '.join(value_list)
        translated_result = translator.translate(joined_list)
        translated_value_list = translated_result.split('|||')

        if len(value_list) != len(translated_value_list):
            translated_value_list = translator.translate_batch(value_list)

        for index, data in enumerate(data_list):
            data['en'] = translated_value_list[index].strip()
        return data_list, True
    except Exception as e:
        return str(e), False

def text_translate_google(text_to_translate, source_langauge, target_language):
    try:
        if text_to_translate == '' or not isinstance(text_to_translate, str):
            return "No Text Provided", True
        text_to_translate = text_to_translate.strip()
        target_language = target_language.strip()
        # Built-in function call handles the text translation matrix locally
        translated_result = GoogleTranslator(source=source_langauge, target=target_language).translate(text_to_translate)
        return translated_result, True
    except Exception as e:
        return str(e), False

def dynamic_sanskrit_transliterate(text, target_lang, source_lang='devanagari'):
    """
    Safely converts Sanskrit text into English, Telugu, or Subscript Tamil.
    """
    # 1. Clean input string and fail early if it's empty
    if not text or not isinstance(text, str):
        return ""

    # 2. Comprehensive dynamic mappings
    scheme_mapping = {
        'en': sanscript.IAST,
        'te': sanscript.TELUGU,
        'ta': sanscript.TAMIL_SUB,       # Subscript numbers (க₂, க₃...)
        'devanagari': sanscript.DEVANAGARI,
        'hi' : sanscript.DEVANAGARI
    }

    # 3. Clean up keys to avoid case-sensitivity issues
    target_key = str(target_lang).lower().strip()
    source_key = str(source_lang).lower().strip()

    # 4. Strict validation checks
    if target_key not in scheme_mapping:
        raise ValueError(f"Invalid target language. Choose from: {list(scheme_mapping.keys())}")
    if source_key not in scheme_mapping:
        raise ValueError(f"Invalid source language. Choose from: {list(scheme_mapping.keys())}")

    # 5. Execute safe translation
    raw_output =  transliterate(text, scheme_mapping[source_key], scheme_mapping[target_key])

    # 2. FIX FOR TAMIL SUB/SUP RENDERING BUGS
    if target_key in ['ta', 'tamil_sup']:
        # Matches any subscript (₂₃₄) or superscript (²³⁴) followed by Tamil combining vowel signs/pulli
        # Tamil Unicode combining character block range: \u0BBE to \u0BCD
        buggy_sequence_pattern = r'([₂₃₄²³⁴])([\u0BBE-\u0BCD]+)'

        # Swaps the vowel sign to come FIRST, and pushes the number modifier to the outside
        raw_output = re.sub(buggy_sequence_pattern, r'\2\1', raw_output)

        # REMOVE THE STUBBORN APOSTROPHES
        # This catches the special modifier apostrophe (ʼ) along with regular ones
        raw_output = raw_output.replace('ʼ', '').replace("'", "").replace("’", "")

    return raw_output

def translate_large_text_with_google(mixed_text, source_lang='en', target_lang='en'):
    try:
        if mixed_text == '' or not isinstance(mixed_text, str):
            return "No Text Provided", True
        # Initialize GoogleTranslator with Sanskrit (sa) and Tamil (ta)
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        cleaned_text = re.sub(r'[\u0980-\u09FF]', '', mixed_text)
        # Split text by sentences to keep translations meaningful
        sentences = cleaned_text.split('. ')

        current_chunk = ""
        translated_chunks = []
        chunk_size = 3500
        for sentence in sentences:
            # Check if adding this sentence stays within our safe limit
            if len(current_chunk) + len(sentence) < chunk_size:
                current_chunk += sentence + ". "
            else:
                # Translate the ready chunk
                print(f"Translating batch ({len(current_chunk)} characters)...")
                translated_text = translator.translate(current_chunk)
                translated_chunks.append(translated_text)

                # Brief pause to avoid hitting Google's rate limits
                time.sleep(1)

                # Start the next chunk
                current_chunk = sentence + ". "

        # Process the final remaining chunk
        if current_chunk:
            translated_text = translator.translate(current_chunk)
            translated_chunks.append(translated_text)

        return " ".join(translated_chunks), True
    except Exception as e:
        return str(e), False

def batch_translate_list_azure(texts, source='en', target='ta', max_retries=3):
    if not texts:
        return [], False

    total_characters = sum(len(text) for text in texts)
    list_length = len(texts)

    if total_characters == 0 or total_characters > 33000 or list_length > 950:
        print(f'Characters or items exceeded: {list_length} items, {total_characters} chars')
        return [], False

    azure_key = os.getenv('AZURE_KEY')
    if not azure_key:
        print('Missing AZURE_KEY environment variable')
        return [], False

    azure_endpoint = "https://api.cognitive.microsofttranslator.com"
    constructed_url = f"{azure_endpoint}/translate"

    headers = {
        'Ocp-Apim-Subscription-Key': azure_key,
        'Ocp-Apim-Subscription-Region': "centralindia",  # Match your exact region
        'Content-type': 'application/json',
        'X-ClientTraceId': str(uuid.uuid4())
    }
    params = {
        'api-version': '3.0',
        'from': source,
        'to': target
    }
    body = [{"text": text} for text in texts]

    for attempt in range(max_retries):
        response = None
        try:
            response = requests.post(constructed_url, params=params, headers=headers, json=body, timeout=(10,60))

            # Handle 429 Rate Limit gracefully using Azure's Retry-After header
            if response.status_code == 429:
                wait_time = int(response.headers.get("Retry-After", 15))
                print(f"Rate limit (429) hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
                continue

            response.raise_for_status()

            results = response.json()
            translations = [item["translations"][0]["text"] for item in results]

            # Optional: print characters billed in this call
            used_chars = response.headers.get("X-Metered-Usage", total_characters)
            print(f"Batch succeeded ({used_chars} chars used)")
            return translations, True

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"Network/Read timeout on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))  # Wait 5s, then 10s before retrying
                continue
            return [], False
        except requests.exceptions.RequestException as e:
            reason = response.reason if response is not None else "No response"
            print(f"API Request Error: {e} ({reason})")
            return [], False
        except (KeyError, IndexError, ValueError) as e:
            print(f"Unexpected response format: {e}")
            return [], False

    print("Failed after maximum retries due to rate limiting.")
    return [], False

def translate_large_list_azure(texts, source='en', target='ta', max_items=250, max_chars=10000):
    """
    Splits lists into fast 250-item / 10,000-char batches so Azure responds quickly
    without read timeouts or 429 rate-limit errors.
    """
    if not texts:
        return [], True

    all_translations = []
    current_batch = []
    current_chars = 0

    for text in texts:
        text_len = len(text)
        if text_len > 48000:
            print(f"Error: Single item length ({text_len}) exceeds Azure limit.")
            return [], False

        if len(current_batch) >= max_items or (current_chars + text_len) > max_chars:
            batch_result, success = batch_translate_list_azure(current_batch, source, target)
            if not success:
                return [], False

            all_translations.extend(batch_result)

            # Pace requests to stay under ~30,000 chars/minute on Free F0 tier
            pace_delay = max(2.0, (current_chars / 1000.0) * 2.0)
            time.sleep(pace_delay)

            current_batch = []
            current_chars = 0

        current_batch.append(text)
        current_chars += text_len

    if current_batch:
        batch_result, success = batch_translate_list_azure(current_batch, source, target)
        if not success:
            return [], False
        all_translations.extend(batch_result)

    return all_translations, True

def translate_api_groq(strings_to_translate: list[str], lang_code: str):
    if not strings_to_translate:
        return 'Not a List Object'
    total_characters = sum(len(text) for text in strings_to_translate)
    if total_characters > 8000:
        return 'Text Can not translated more than 8000 characters.'
    supported_languages = {
        "en": "English",
        "sa": "Sanskrit (संस्कृत)",
        "hi": "Hindi (हिंदी)",
        "ta": "Tamil (தமிழ்)",
        "te": "Telugu (తెలుగు)",
        "kn": "Kannada (ಕನ್ನಡ)",
        "ml": "Malayalam (മലയാളം)"
    }
    target_lang = supported_languages.get(lang_code)
    if not target_lang:
        return "error: Supported Langauges are en(English), sa(Sanskrit), ta(Tamil), te(Telugu), kn(Kannada), ml(Malayalam)"

    system_prompt = (
        f"You are an expert translator fluent in English, Sanskrit, and {target_lang}. "
        f"Translate the user's input array of strings in 'texts' accurately into clear, natural {target_lang} using its native script. "
        "You MUST respond with a valid JSON object containing a single key 'translations' whose value is an array of strings. "
        "Maintain the exact same number of elements and exact same order as the input array. "
        "Do not merge, split, or skip any strings."
        "If the input is a spiritual or Bhagavad Gita text, preserve traditional philosophical terms accurately. "
        f"Use authentic spiritual and Vedantic {target_lang} vocabulary—for example: "
        "translate 'sannyasa' as 'சந்நியாசம்' or 'துறவு', 'tyaga' as 'தியாகம்' or 'பற்றின்மை' (never modern words like 'விடுப்பு'), "
        "'atman' as 'ஆத்மா', 'dharma' as 'தர்மம்', 'karma' as 'கர்மம்', 'yoga' as 'யோகம்', "
        "If the input is general English content, keep the tone natural, clear, and culturally appropriate. "
        f"Return only the {target_lang} translation with standard spaces and no extra English commentary."
    )
    system_prompt_2 = (
        "You are a revered Sanskrit and Tamil scholar specializing in the Srimad Bhagavad Gita. "
        "For the given Sanskrit shloka, provide the output strictly in Tamil using these two sections:\n\n"
        "பதவுரை (சொற்பொருள்):\n"
        "- Break down each key Sanskrit word/compound in Tamil script followed by its exact Tamil meaning.\n\n"
        "பொழிப்புரை (மொழிபெயர்ப்பு):\n"
        "- Provide a clear, devotional, and accurate Tamil translation of the full verse.\n\n"
        "Rules:\n"
        "1. Use authentic spiritual Tamil terms (e.g., 'துறவு' for sannyasa, 'தியாகம்' for tyaga, 'ரிஷிகேசா' for Hrishikesha).\n"
        "2. Never use modern bureaucratic words (like 'விடுப்பு' for tyaga) or any English words.\n"
        "3. Use standard spaces only."
    )
    system_prompt_2 = (
        f"You are an expert translator fluent in English, Sanskrit, and {target_lang}. "
        f"Translate the user's input text accurately into clear, natural {target_lang} using its native script. "
        "If the input is a spiritual or Bhagavad Gita text, preserve traditional philosophical terms accurately. "
        f"Use authentic spiritual and Vedantic {target_lang} vocabulary—for example: "
        "translate 'sannyasa' as 'சந்நியாசம்' or 'துறவு', 'tyaga' as 'தியாகம்' or 'பற்றின்மை' (never modern words like 'விடுப்பு'), "
        "'atman' as 'ஆத்மா', 'dharma' as 'தர்மம்', 'karma' as 'கர்மம்', 'yoga' as 'யோகம்', "
        "If the input is general English content, keep the tone natural, clear, and culturally appropriate. "
        f"Return only the {target_lang} translation with standard spaces and no extra English commentary."
    )
    groq_api_key = os.environ.get("GROQ_API_KEY")
    groq_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"texts": strings_to_translate}, ensure_ascii=False)}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "reasoning_effort" : "low"
    }

    try:
        response = requests.post(groq_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        raw_content = result["choices"][0]["message"]["content"]
        translated_strings = json.loads(raw_content).get("translations", [])
        # Validate 1-to-1 length match
        if len(translated_strings) != len(strings_to_translate):
            raise ValueError(
                f"Translation mismatch: sent {len(strings_to_translate)}, got {len(translated_strings)}"
            )
        translated_strings = remove_non_printable_from_object(translated_strings)
        return translated_strings
    except (requests.exceptions.RequestException, ValueError, json.JSONDecodeError, KeyError) as e:
        return f"error: {str(e)}"