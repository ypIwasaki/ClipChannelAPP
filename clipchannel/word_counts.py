"""Count words in a saved, corrected target-speaker transcript."""

from collections import defaultdict

from .storage import StorageError, result_relative_path


class WordCountError(StorageError):
    pass


def _tokenizer():
    try:
        from sudachipy import dictionary, tokenizer
        return dictionary.Dictionary().create(), tokenizer.Tokenizer.SplitMode.C
    except (ImportError, OSError, RuntimeError) as error:
        raise WordCountError("再集計には SudachiPy と SudachiDict-core が必要です") from error


def count_words(data, video, transcript_version, *, include_verbs=False, include_adjectives=False):
    """Save a new CSV version; each row links one distinct utterance to a word."""
    if not isinstance(transcript_version, int) or transcript_version < 1:
        raise WordCountError("文字起こしの版が不正です")
    analyzer, mode = _tokenizer()
    registered = {row["word"] for row in data.load_shared("registered-words") if row["word"]}
    excluded = {row["word"] for row in data.load_shared("excluded-words") if row["word"]}
    transcript = data.load_result(video, "transcripts", transcript_version)
    allowed = {"名詞"}
    if include_verbs:
        allowed.add("動詞")
    if include_adjectives:
        allowed.add("形容詞")
    totals = defaultdict(int)
    hits = defaultdict(list)
    for row in transcript:
        if row["speaker_id"] != "target" or not row["text"]:
            continue
        sentence = row["text"]
        words = []
        offset = 0
        while offset < len(sentence):
            match = max((word for word in registered if sentence.startswith(word, offset)), key=len, default=None)
            if match:
                words.append(match)
                offset += len(match)
                continue
            next_registered = min((sentence.find(word, offset) for word in registered
                                   if sentence.find(word, offset) >= 0), default=len(sentence))
            boundary = max(offset + 1, next_registered)
            for token in analyzer.tokenize(sentence[offset:boundary], mode):
                if token.part_of_speech()[0] in allowed:
                    # dictionary form only collects inflections; normalized_form may merge spellings.
                    words.append(token.surface() if token.part_of_speech()[0] == "名詞"
                                 else token.dictionary_form())
            offset = boundary
        for word in words:
            if word not in excluded:
                totals[word] += 1
        for word in set(words) - excluded:
            hits[word].append(row)
    rows = []
    for word in sorted(hits, key=lambda item: (-totals[item], item)):
        for utterance in hits[word]:
            rows.append({"word": word, "occurrences": str(totals[word]),
                         "utterances": str(len(hits[word])), "start_ms": utterance["start_ms"],
                         "end_ms": utterance["end_ms"], "text": utterance["text"],
                         "transcript_version": str(transcript_version),
                         "include_verbs": str(int(include_verbs)),
                         "include_adjectives": str(int(include_adjectives))})
    source_result = result_relative_path(video, "transcripts", transcript_version)
    return data.save_result(video, "word-counts", rows, references=(("results", source_result),))
