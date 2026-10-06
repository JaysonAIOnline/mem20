from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'runtime'))
from mem20humancapabilitysuperplatformz import main
if __name__=='__main__': main(str(HERE/'CAPABILITY.json'))
