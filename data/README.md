# Data

This directory contains the MRCMPSP instances used by the computational experiments, converted to the JSON format read by `src/Instance.py`. The files are included locally so the experiment scripts can run without downloading or parsing the original instance files at execution time.

## Included Instances

- `MISTA/`: the 30 benchmark instances from the MISTA 2013 challenge (Wauters et al. 2016).
- `MISTA_AB/`: 60 additional instances derived from the MISTA benchmark set by systematically varying the capacities of the global resources (two variants, `_a` and `_b`, per base instance).

## Citations and License

Please cite the original instance set when reusing these files:

- Wauters, T., Kinable, J., Smet, P., Vancroonenburg, W., Vanden Berghe, G., & Verstichel, J. (2016). The multi-mode resource-constrained multi-project scheduling problem: The MISTA 2013 challenge. *Journal of Scheduling*, 19(3), 271–283.

Original MISTA 2013 challenge instances: https://gent.cs.kuleuven.be/mista2013challenge/instances.html

The instances in `MISTA_AB/` are derived from the above data set for this paper; see the paper's supplemental material for details of the generation procedure.

### Data License

The MISTA 2013 challenge website does not publish a formal license or terms
of use for the instance files. The organizers state only that the datasets
were made publicly available "to stimulate further research on the
MRCMPSP" and ask that the challenge paper (cited above) be cited when
referring to the problem, datasets, or results. Local copies are included
here, under that citation request, solely to support replication of the
computational experiments in this paper. This repository's [MIT
License](../LICENSE) applies to the code only, not to these third-party
data files. If you intend to reuse this data beyond replicating this paper,
please cite the original publication and consider contacting the MISTA
2013 challenge organizers.
