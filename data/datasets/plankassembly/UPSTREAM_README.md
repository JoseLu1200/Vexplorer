---
license: cc-by-nc-nd-4.0
size_categories:
- 10K<n<100K
---

# PlankAssembly Dataset

If you encounter downloading issue, you can directly download the dataset [here](https://manycore-research-azure.kujiale.com/manycore-research/PlankAssembly/data.zip).

## Dataset Description

- **Homepage:** https://manycore-research.github.io/PlankAssembly
- **Repository:** https://github.com/manycore-research/PlankAssembly
- **Paper:** https://arxiv.org/abs/2308.05744

### Dataset Summary

This is the dataset used for training [PlankAssembly](https://manycore-research.github.io/PlankAssembly). It contains 26,707 shape programs derived from parametric CAD models.

## Dataset Structure

PlankAssembly dataset is a directory with the following structure:

    PlankAssemblyDataset
    ├── model               # shape program
    |   └── <MODLE_ID>.json
    └── splits              # dataset splits
        ├── train.txt
        ├── valid.txt
        └── test.txt

## PlankAssembly DSL

A cabinet is typically assembled by a list of plank models, where each plank is represented as an axis-aligned cuboid. A cuboid has six degrees of freedom, which correspond to the starting and ending coordinates along the three axes:
```
Cuboid (x_min, y_min, z_min, x_max, y_max, z_max).
```
Each coordinate can either take a numerical value or be a pointer to the corresponding coordinate of another cuboid (to which it attaches to).

In the parametric modeling software, a plank is typically created by first drawing a 2D profile and then applying the extrusion command. Thus, we categorize the faces of each plank into *sideface* or *endface*, depending on whether they are along the direction of the extrusion or not. Then, given a pair of faces from two different planks, we consider that an attachment relationship exists if (i) the two faces are within a distance threshold of 1mm and (ii) the pair consists of one sideface and one endface.

## Shape Program

Each shape program (*model.json*) is a JSON file with the following structure:

```python
{
  # model id
  "name": str,
  # numerical values of all planks, the units are millimeters
  "planks": List[List],         # N x 6
  # extrusion direction of each plank
  "normal": List[List],         # N x 3
  # attachment relationships
  # -1 denotes no attachment relationship
  # Others denote the index of the flattened plank sequence
  "attach": List[List],         # N x 6
}
```

## BibTex

Please cite our paper if you use PlankAssembly dataset in your work:

```bibtex
@inproceedings{PlankAssembly,
  author    = {Hu, Wentao and Zheng, Jia and Zhang, Zixin and Yuan, Xiaojun and Yin, Jian and Zhou, Zihan},
  title     = {PlankAssembly: Robust 3D Reconstruction from Three Orthographic Views with Learnt Shape Programs},
  booktitle = {ICCV},
  year      = {2023}
}
```