# Scripts

This directory contains helper scripts used for experiment preparation, data processing, and visualization.

These scripts support the experimental workflow but are not part of the cryptographic implementation.

## Purpose

Scripts are mainly used for:

- Parameter validation
- Experimental data processing
- Result generation
- Visualization generation

## Relationship with Experiments

The general workflow is:

```
Experiment Execution
        |
        v
Raw Measurements
        |
        v
Scripts Processing
        |
        v
Results Tables and Figures
```

## Notes

Scripts are designed to improve reproducibility of experiments.

They do not modify the underlying Sapling proving algorithm or cryptographic logic.