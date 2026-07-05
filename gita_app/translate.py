import re
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from deep_translator import GoogleTranslator


def batch_translate_google(data_list, source_langauge, target_language):
    translator = GoogleTranslator(source=source_langauge, target=target_language)
    value_list = [data['en'].strip() for data in data_list]
    translated_value_list = translator.translate_batch(value_list)
    for index, data in enumerate(data_list):
        data['en'] = translated_value_list[index]
    return data_list

def text_translate_google(text_to_translate, source_langauge, target_language):
    text_to_translate = text_to_translate.strip()
    target_language = target_language.strip()
    # Built-in function call handles the text translation matrix locally
    translated_result = GoogleTranslator(source=source_langauge, target=target_language).translate(text_to_translate)
    return translated_result

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