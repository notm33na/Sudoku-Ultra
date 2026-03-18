#!/usr/bin/env python3
"""
Train the Sudoku GAN (WGAN-GP).

Usage:
    python ml/scripts/train_gan.py \
        --epochs 200 \
        --batch-size 64 \
        --latent-dim 64 \
        --output ml/models/sudoku_gan_generator.pt \
        --export-onnx

Training data is generated on-the-fly using a backtracking solver
(no external dataset required).

The generator is saved as a PyTorch state_dict (.pt) and optionally
exported to ONNX for cross-platform serving.
"""

import argparse
import os
import sys
import time
from pathlib import Path

import torch
import torch.optim as optim

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "ml-service"))

from app.ml.gan import (
    LATENT_DIM,
    NUM_DIFFICULTIES,
    SudokuDiscriminator,
    SudokuGenerator,
    generate_training_batch,
    gradient_penalty,
)


# ── Training loop ─────────────────────────────────────────────────────────────

def train(
    epochs: int,
    batch_size: int,
    latent_dim: int,
    n_critic: int,
    gp_lambda: float,
    lr: float,
    output_path: Path,
    export_onnx: bool,
    device: torch.device,
) -> None:
    print(f"Device: {device}")
    print(f"Epochs: {epochs}  Batch: {batch_size}  Latent: {latent_dim}")

    gen = SudokuGenerator(latent_dim, NUM_DIFFICULTIES).to(device)
    disc = SudokuDiscriminator().to(device)

    opt_g = optim.Adam(gen.parameters(), lr=lr, betas=(0.5, 0.9))
    opt_d = optim.Adam(disc.parameters(), lr=lr, betas=(0.5, 0.9))

    best_g_loss = float("inf")
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        # ── Train discriminator n_critic times per generator step ──────────
        d_loss_total = 0.0
        for _ in range(n_critic):
            real, diff_idx = generate_training_batch(batch_size, device)
            z = gen.sample_z(batch_size, device)

            with torch.no_grad():
                fake_logits = gen(z, diff_idx)
                import torch.nn.functional as F
                fake = F.softmax(fake_logits, dim=-1)

            d_real = disc(real).mean()
            d_fake = disc(fake).mean()
            gp = gradient_penalty(disc, real, fake, device)
            d_loss = -d_real + d_fake + gp_lambda * gp

            opt_d.zero_grad()
            d_loss.backward()
            opt_d.step()
            d_loss_total += d_loss.item()

        # ── Train generator ────────────────────────────────────────────────
        z = gen.sample_z(batch_size, device)
        _, diff_idx = generate_training_batch(batch_size, device)
        import torch.nn.functional as F
        fake_logits = gen(z, diff_idx)
        fake = F.softmax(fake_logits, dim=-1)
        g_loss = -disc(fake).mean()

        opt_g.zero_grad()
        g_loss.backward()
        opt_g.step()

        g_loss_val = g_loss.item()
        if epoch % 10 == 0 or epoch == 1:
            elapsed = time.time() - t0
            print(
                f"Epoch {epoch:4d}/{epochs} | "
                f"D_loss: {d_loss_total/n_critic:+.4f} | "
                f"G_loss: {g_loss_val:+.4f} | "
                f"Elapsed: {elapsed:.0f}s"
            )

        if g_loss_val < best_g_loss:
            best_g_loss = g_loss_val
            torch.save(gen.state_dict(), output_path)

    print(f"\nBest G loss: {best_g_loss:.4f}")
    print(f"Generator saved → {output_path}")

    # ── ONNX export ────────────────────────────────────────────────────────
    if export_onnx:
        onnx_path = output_path.with_suffix(".onnx")
        gen.eval()
        dummy_z = torch.randn(1, latent_dim)
        dummy_diff = torch.zeros(1, dtype=torch.long)
        torch.onnx.export(
            gen,
            (dummy_z, dummy_diff),
            str(onnx_path),
            input_names=["z", "difficulty"],
            output_names=["logits"],
            dynamic_axes={"z": {0: "batch"}, "difficulty": {0: "batch"}, "logits": {0: "batch"}},
            opset_version=17,
        )
        print(f"ONNX export → {onnx_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Train Sudoku GAN (WGAN-GP)")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--latent-dim", type=int, default=LATENT_DIM)
    parser.add_argument("--n-critic", type=int, default=5, help="Discriminator steps per generator step")
    parser.add_argument("--gp-lambda", type=float, default=10.0, help="Gradient penalty coefficient")
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("ml/models/sudoku_gan_generator.pt"),
    )
    parser.add_argument("--export-onnx", action="store_true")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    args = parser.parse_args()

    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    train(
        epochs=args.epochs,
        batch_size=args.batch_size,
        latent_dim=args.latent_dim,
        n_critic=args.n_critic,
        gp_lambda=args.gp_lambda,
        lr=args.lr,
        output_path=args.output,
        export_onnx=args.export_onnx,
        device=device,
    )


if __name__ == "__main__":
    main()
