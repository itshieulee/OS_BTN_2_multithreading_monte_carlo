from pathlib import Path
from analyze import main
from plot_sections import generate

if __name__ == "__main__":
    main()
    generate(Path(__file__).resolve().parents[1])
