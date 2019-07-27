import pytest

from sklearn.utils.estimator_checks import check_estimator

from sklearn_extra.kernel_approximation import Fastfood
from sklearn_extra.cluster import KMedoids


@pytest.mark.parametrize("Estimator", [Fastfood, KMedoids])
def test_all_estimators(Estimator, request):
    return check_estimator(Estimator)
