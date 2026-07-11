import re, time
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from deep_translator import GoogleTranslator

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
        'devanagari': sanscript.DEVANAGARI
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