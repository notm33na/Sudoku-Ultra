"""
train_toxicity.py — Fine-tune DistilBERT for chat toxicity classification.

Dataset : HuggingFace `civil_comments` (public, no Kaggle auth required)
           Toxicity column is a float 0–1; threshold ≥ 0.5 → toxic (label=1)
Model   : distilbert-base-uncased → DistilBertForSequenceClassification (2 labels)
Output  : ml/models/toxicity_classifier/  (model + tokenizer saved via .save_pretrained)

Usage:
    python -m app.ml.train_toxicity

MLflow metrics logged:
    eval_f1, eval_accuracy, eval_precision, eval_recall, training_seconds
"""

from __future__ import annotations

import logging
import pathlib
import time
from typing import Any

import mlflow
import numpy as np

logger = logging.getLogger(__name__)

MODEL_DIR = pathlib.Path("ml/models/toxicity_classifier")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

BASE_MODEL = "distilbert-base-uncased"
MAX_SEQ_LEN = 128
TOXICITY_THRESHOLD = 0.5


def train_and_save(
    train_size: int = 20_000,
    eval_size: int = 2_000,
    num_epochs: int = 2,
    batch_size: int = 32,
    learning_rate: float = 2e-5,
) -> dict[str, Any]:
    """
    Fine-tune DistilBERT on civil_comments; save model + tokenizer.
    Returns metric dict: {eval_f1, eval_accuracy, eval_precision, eval_recall}.
    """
    try:
        from datasets import load_dataset
        from transformers import (
            DistilBertForSequenceClassification,
            DistilBertTokenizerFast,
            Trainer,
            TrainingArguments,
        )
        import evaluate
    except ImportError as exc:
        raise RuntimeError(
            "transformers, datasets, and evaluate are required. "
            "pip install transformers datasets evaluate accelerate"
        ) from exc

    logger.info("Loading civil_comments dataset …")
    raw = (
        load_dataset("civil_comments", split="train")
        .shuffle(seed=42)
        .select(range(train_size + eval_size))
    )
    train_ds = raw.select(range(train_size))
    eval_ds = raw.select(range(train_size, train_size + eval_size))

    logger.info(f"Train: {len(train_ds)}, Eval: {len(eval_ds)}")

    tokenizer = DistilBertTokenizerFast.from_pretrained(BASE_MODEL)

    def _tokenize(batch):
        tokens = tokenizer(
            batch["text"],
            truncation=True,
            padding="max_length",
            max_length=MAX_SEQ_LEN,
        )
        tokens["labels"] = [int(t >= TOXICITY_THRESHOLD) for t in batch["toxicity"]]
        return tokens

    train_tokenized = train_ds.map(_tokenize, batched=True, remove_columns=train_ds.column_names)
    eval_tokenized = eval_ds.map(_tokenize, batched=True, remove_columns=eval_ds.column_names)

    model = DistilBertForSequenceClassification.from_pretrained(BASE_MODEL, num_labels=2)

    # ── Metrics ───────────────────────────────────────────────────────────────
    f1_metric = evaluate.load("f1")
    acc_metric = evaluate.load("accuracy")
    prec_metric = evaluate.load("precision")
    rec_metric = evaluate.load("recall")

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "f1":        f1_metric.compute(predictions=preds, references=labels, average="binary")["f1"],
            "accuracy":  acc_metric.compute(predictions=preds, references=labels)["accuracy"],
            "precision": prec_metric.compute(predictions=preds, references=labels, average="binary")["precision"],
            "recall":    rec_metric.compute(predictions=preds, references=labels, average="binary")["recall"],
        }

    # ── Training Args ─────────────────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=str(MODEL_DIR),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1",
        greater_is_better=True,
        logging_steps=200,
        report_to="none",  # we log to MLflow manually
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_tokenized,
        eval_dataset=eval_tokenized,
        compute_metrics=compute_metrics,
    )

    # ── Train ─────────────────────────────────────────────────────────────────
    t0 = time.time()
    with mlflow.start_run(run_name="toxicity_classifier") as _run:
        mlflow.log_params({
            "base_model":    BASE_MODEL,
            "train_size":    train_size,
            "eval_size":     eval_size,
            "num_epochs":    num_epochs,
            "batch_size":    batch_size,
            "learning_rate": learning_rate,
            "max_seq_len":   MAX_SEQ_LEN,
            "threshold":     TOXICITY_THRESHOLD,
        })

        trainer.train()
        elapsed = time.time() - t0

        eval_results = trainer.evaluate()
        metrics = {
            "eval_f1":        eval_results.get("eval_f1", 0.0),
            "eval_accuracy":  eval_results.get("eval_accuracy", 0.0),
            "eval_precision": eval_results.get("eval_precision", 0.0),
            "eval_recall":    eval_results.get("eval_recall", 0.0),
            "training_seconds": elapsed,
        }
        mlflow.log_metrics(metrics)

        # Save fine-tuned model + tokenizer
        model.save_pretrained(str(MODEL_DIR))
        tokenizer.save_pretrained(str(MODEL_DIR))
        mlflow.log_artifact(str(MODEL_DIR))

        logger.info(
            f"Toxicity classifier trained in {elapsed:.1f}s | "
            f"F1={metrics['eval_f1']:.3f} | Accuracy={metrics['eval_accuracy']:.3f}"
        )

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    train_and_save()
