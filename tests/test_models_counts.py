# -*- coding: utf-8 -*-
from pdf_agent_translator.models import (
    BlockStatus,
    Document,
    SourceBlock,
    TargetBlock,
    TranslationPair,
    refresh_translation_counts,
)


def test_counts_split_skip_and_translated() -> None:
    doc = Document(
        job_id="j",
        source_pdf_name="a.pdf",
        pairs=[
            TranslationPair(
                source=SourceBlock(block_id="a", index=0, markdown="hi"),
                target=TargetBlock(markdown="嗨", status=BlockStatus.translated),
            ),
            TranslationPair(
                source=SourceBlock(block_id="b", index=1, markdown="fig"),
                target=TargetBlock(markdown="fig", status=BlockStatus.skipped, skip_kind="deterministic"),
            ),
        ],
    )
    refresh_translation_counts(doc)
    assert doc.translation.translated == 1
    assert doc.translation.skipped == 1
    assert doc.translation.pending == 0
