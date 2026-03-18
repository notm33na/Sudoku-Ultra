"""
GAN training — callable train_and_save() for the mlops retrain endpoint.

Wraps the WGAN-GP training loop from app.ml.gan. Uses lightweight defaults
(50 epochs) suitable for scheduled retraining; override via arguments for
full production training runs.
"""

from __future__ import annotations

import time
from pathlib import Path

import torch
import torch.nn.functional as F
import torch.optim as optim

from app.ml.gan import (
    LATENT_DIM,
    NUM_DIFFICULTIES,
    SudokuDiscriminator,
    SudokuGenerator,
    generate_training_batch,
    gradient_penalty,
)
from app.logging import setup_logging

logger = setup_logging()

OUTPUT_PATH = Path("ml/models/sudoku_gan_generator.pt")


def train_and_save(
    epochs: int = 50,
    batch_size: int = 64,
    n_critic: int = 5,
    gp_lambda: float = 10.0,
    lr: float = 1e-4,
    output_path: Path | None = None,
) -> dict:
    """
    Train the Sudoku WGAN-GP generator and save the best checkpoint.

    Returns a metrics dict with best_g_loss and epochs_trained.
    """
    output_path = output_path or OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"GAN training: device={device} epochs={epochs} batch={batch_size}")

    gen  = SudokuGenerator(LATENT_DIM, NUM_DIFFICULTIES).to(device)
    disc = SudokuDiscriminator().to(device)

    opt_g = optim.Adam(gen.parameters(), lr=lr, betas=(0.5, 0.9))
    opt_d = optim.Adam(disc.parameters(), lr=lr, betas=(0.5, 0.9))

    best_g_loss = float("inf")
    t0 = time.time()

    for epoch in range(1, epochs + 1):
        # ── Discriminator steps ────────────────────────────────────────────
        d_loss_total = 0.0
        for _ in range(n_critic):
            real, diff_idx = generate_training_batch(batch_size, device)
            z = gen.sample_z(batch_size, device)

            with torch.no_grad():
                fake = F.softmax(gen(z, diff_idx), dim=-1)

            d_real = disc(real).mean()
            d_fake = disc(fake).mean()
            gp     = gradient_penalty(disc, real, fake, device)
            d_loss = -d_real + d_fake + gp_lambda * gp

            opt_d.zero_grad()
            d_loss.backward()
            opt_d.step()
            d_loss_total += d_loss.item()

        # ── Generator step ────────────────────────────────────────────────
        z = gen.sample_z(batch_size, device)
        _, diff_idx = generate_training_batch(batch_size, device)
        fake  = F.softmax(gen(z, diff_idx), dim=-1)
        g_loss = -disc(fake).mean()

        opt_g.zero_grad()
        g_loss.backward()
        opt_g.step()

        g_val = g_loss.item()
        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                f"Epoch {epoch:4d}/{epochs} | "
                f"D_loss: {d_loss_total/n_critic:+.4f} | "
                f"G_loss: {g_val:+.4f} | "
                f"Elapsed: {time.time()-t0:.0f}s"
            )

        if g_val < best_g_loss:
            best_g_loss = g_val
            torch.save(gen.state_dict(), output_path)

    logger.info(f"GAN training complete: best_g_loss={best_g_loss:.4f} → {output_path}")
    return {
        "best_g_loss": round(best_g_loss, 4),
        "epochs_trained": epochs,
    }
