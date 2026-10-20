"""
tests/test_colab_importer.py
Comprehensive unit tests for Colab artifact organization and dummy vector scoring.
"""

from pathlib import Path
import shutil
import tempfile
import unittest

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier

from src.import_colab_artifacts import (
    ARTIFACT_TARGET_MAPPING,
    DUMMY_TEST_VECTOR,
    FEATURE_NAMES,
    compute_file_sha256,
    find_staged_artifact,
    organize_artifacts,
    score_dummy_vector,
)


class TestColabArtifactImporter(unittest.TestCase):
    """Test suite for Colab artifact organizer, staging search, and model scoring."""

    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp(prefix="test_colab_import_"))
        self.staging_dir = self.temp_root / "downloads"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        # Create dummy models to test scoring
        self.iso_model = IsolationForest(n_estimators=10, random_state=42)
        X_dummy = pd.DataFrame(
            [[20.0, 1.0, 0.0, 1.0, 0.1, 0.2], [15.0, 6.0, 0.2, 5.5, 1.2, 2.5]],
            columns=FEATURE_NAMES,
        )
        self.iso_model.fit(X_dummy)

        self.rf_model = RandomForestClassifier(n_estimators=10, random_state=42)
        y_dummy = ["normal", "partial_bypass"]
        self.rf_model.fit(X_dummy, y_dummy)

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_find_staged_artifact(self):
        """Verifies finding uploaded files in search directories."""
        test_file = self.staging_dir / "isolation_forest.joblib"
        test_file.write_text("dummy", encoding="utf-8")

        found = find_staged_artifact("isolation_forest.joblib", [self.staging_dir, self.temp_root])
        self.assertIsNotNone(found)
        self.assertEqual(found, test_file)

        not_found = find_staged_artifact("missing_file.csv", [self.staging_dir])
        self.assertIsNone(not_found)

    def test_organize_staged_artifacts(self):
        """Verifies moving artifacts from staging directory to target destinations."""
        # Stage artifacts in temporary downloads
        joblib.dump(self.iso_model, self.staging_dir / "isolation_forest.joblib")
        joblib.dump(self.rf_model, self.staging_dir / "random_forest.joblib")

        df = pd.DataFrame({"actual_pressure": [20.0], "hydraulic_residual": [1.0]})
        df.to_csv(self.staging_dir / "training_features.csv", index=False)

        (self.staging_dir / "confusion_matrix.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        # Organize with staging search into temp_root
        results = organize_artifacts(staging_dirs=[self.staging_dir], dest_root=self.temp_root)

        self.assertIn("isolation_forest.joblib", results)
        self.assertIn("random_forest.joblib", results)
        self.assertIn("training_features.csv", results)
        self.assertIn("confusion_matrix.png", results)

        # Confirm target paths exist under self.temp_root
        self.assertTrue((self.temp_root / "models" / "isolation_forest.joblib").exists())
        self.assertTrue((self.temp_root / "models" / "random_forest.joblib").exists())
        self.assertTrue((self.temp_root / "data" / "processed" / "training_features.csv").exists())
        self.assertTrue((self.temp_root / "reports" / "figures" / "confusion_matrix.png").exists())

    def test_dummy_vector_scoring(self):
        """Verifies that loaded models score [[20.0, 1.2, 0.05, 1.1, 0.2, 0.4]] without errors."""
        scoring = score_dummy_vector(DUMMY_TEST_VECTOR)

        self.assertTrue(scoring["overall_success"], f"Errors encountered: {scoring['errors']}")
        self.assertTrue(scoring["stage1_isolation_forest"]["loaded"])
        self.assertTrue(scoring["stage2_random_forest"]["loaded"])

        # Check prediction results
        self.assertIn(scoring["stage1_isolation_forest"]["raw_prediction"], [1, -1])
        self.assertIn("predicted_class", scoring["stage2_random_forest"])
        self.assertIn("class_probabilities", scoring["stage2_random_forest"])

    def test_compute_sha256(self):
        """Verifies file checksum calculation."""
        test_file = self.temp_root / "sample.txt"
        test_file.write_text("Hello NWSDB Water Fraud C2", encoding="utf-8")
        sha = compute_file_sha256(test_file)
        self.assertIsInstance(sha, str)
        self.assertEqual(len(sha), 64)


if __name__ == "__main__":
    unittest.main()
