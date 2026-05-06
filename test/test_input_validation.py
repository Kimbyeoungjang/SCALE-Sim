import tempfile
import unittest
from pathlib import Path

from scalesim.layout_utils import layouts
from scalesim.scale_sim import scalesim
from scalesim.topology_utils import topologies


class InputValidationTests(unittest.TestCase):
    def test_conv_topology_without_trailing_comma(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            topo_path = Path(tmpdir) / "topo.csv"
            topo_path.write_text(
                "Layer name,IFMAP Height,IFMAP Width,Filter Height,Filter Width,Channels,Num Filter,Strides,Sparsity\n"
                "Conv1,8,8,3,3,1,4,1,1:2\n",
                encoding="utf-8",
            )

            topo = topologies()
            topo.load_arrays(str(topo_path))

            self.assertEqual(topo.get_num_layers(), 1)
            self.assertEqual(topo.get_layer_name(0), "Conv1")
            self.assertEqual(topo.get_layer_sparsity_ratio(0), [1, 2])

    def test_layout_without_trailing_comma(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            layout_path = Path(tmpdir) / "layout.csv"
            layout_path.write_text(
                "Layer name," + ",".join(f"Field{i}" for i in range(20)) + "\n"
                "Conv1," + ",".join("1" for _ in range(20)) + "\n",
                encoding="utf-8",
            )

            layout = layouts()
            layout.load_arrays(str(layout_path))

            self.assertEqual(layout.get_num_layers(), 1)
            self.assertEqual(layout.get_layer_name(0), "Conv1")

    def test_layout_topology_name_mismatch_fails_early(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg_path = root / "scale.cfg"
            topo_path = root / "topo.csv"
            layout_path = root / "layout.csv"

            cfg_path.write_text(
                "[general]\n"
                "run_name = mismatch_test\n"
                "\n"
                "[architecture_presets]\n"
                "ArrayHeight: 4\n"
                "ArrayWidth: 4\n"
                "IfmapSramSzkB: 4\n"
                "FilterSramSzkB: 4\n"
                "OfmapSramSzkB: 4\n"
                "IfmapOffset: 0\n"
                "FilterOffset: 100\n"
                "OfmapOffset: 200\n"
                "Bandwidth: 4\n"
                "Dataflow: ws\n"
                "\n"
                "[layout]\n"
                "IfmapCustomLayout: True\n"
                "FilterCustomLayout: False\n"
                "\n"
                "[run_presets]\n"
                "InterfaceBandwidth: CALC\n",
                encoding="utf-8",
            )

            topo_path.write_text(
                "Layer name,IFMAP Height,IFMAP Width,Filter Height,Filter Width,Channels,Num Filter,Strides,Sparsity,\n"
                "Conv1,8,8,3,3,1,4,1,1:1,\n",
                encoding="utf-8",
            )
            layout_path.write_text(
                "Layer name," + ",".join(f"Field{i}" for i in range(20)) + ",\n"
                "OtherLayer," + ",".join("1" for _ in range(20)) + ",\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "layer name mismatch"):
                scalesim(
                    config=str(cfg_path),
                    topology=str(topo_path),
                    layout=str(layout_path),
                )

    def test_layout_name_mismatch_allowed_when_custom_layout_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cfg_path = root / "scale.cfg"
            topo_path = root / "topo.csv"
            layout_path = root / "layout.csv"

            cfg_path.write_text(
                "[general]\n"
                "run_name = mismatch_disabled_test\n"
                "\n"
                "[architecture_presets]\n"
                "ArrayHeight: 4\n"
                "ArrayWidth: 4\n"
                "IfmapSramSzkB: 4\n"
                "FilterSramSzkB: 4\n"
                "OfmapSramSzkB: 4\n"
                "IfmapOffset: 0\n"
                "FilterOffset: 100\n"
                "OfmapOffset: 200\n"
                "Bandwidth: 4\n"
                "Dataflow: ws\n"
                "\n"
                "[layout]\n"
                "IfmapCustomLayout: False\n"
                "FilterCustomLayout: False\n"
                "\n"
                "[run_presets]\n"
                "InterfaceBandwidth: CALC\n",
                encoding="utf-8",
            )

            topo_path.write_text(
                "Layer name,IFMAP Height,IFMAP Width,Filter Height,Filter Width,Channels,Num Filter,Strides,Sparsity\n"
                "Conv1,8,8,3,3,1,4,1,1:1\n",
                encoding="utf-8",
            )
            layout_path.write_text(
                "Layer name," + ",".join(f"Field{i}" for i in range(20)) + "\n"
                "OtherLayer," + ",".join("1" for _ in range(20)) + "\n",
                encoding="utf-8",
            )

            scalesim(
                config=str(cfg_path),
                topology=str(topo_path),
                layout=str(layout_path),
            )


if __name__ == "__main__":
    unittest.main()
