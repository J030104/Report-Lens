"""Create a public, native LaTeX comparison from an invented garden report."""
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import subprocess

from reportlens.repository import Config
from reportlens.service import Service


def source(revised=False):
    return r'''\documentclass[12pt,a4paper]{report}
\usepackage[margin=27mm]{geometry}
\usepackage[T1]{fontenc}\usepackage{lmodern}
\usepackage{xcolor,graphicx,float,booktabs,hyperref}
\setlength{\parindent}{0pt}\setlength{\parskip}{0.6em}
\begin{document}
\chapter{A small garden, measured}
\section{Method}
The study follows ''' + ('six raised beds over eight weeks.' if revised else 'four raised beds over six weeks.') + r'''
We record soil moisture before watering each morning.

''' + ('The revised method includes a weekly calibration check.' if revised else 'The initial method uses a single calibration at setup.') + r'''

These invented observations demonstrate a report comparison.
\begin{figure}[H]\centering
\fbox{\begin{minipage}{0.8\linewidth}\centering
Read sensor\par\medskip$\downarrow$\par\medskip
''' + ('Check calibration' if revised else 'Average readings') + r'''
\par\medskip$\downarrow$\par\medskip Save daily record
\end{minipage}}
\caption{Complete daily measurement workflow.}\label{fig:workflow}
\end{figure}
\section{Observations}
Figure~\ref{fig:workflow} shows the workflow. Table~\ref{tab:observations} gives the complete observations.
\begin{table}[H]\centering
\caption{Invented measurements for demonstration only.}\label{tab:observations}
\begin{tabular}{lcc}\toprule
Bed & Mean moisture & Observations\\\midrule
A & ''' + ('41' if revised else '38') + r'''\% & 7\\
B & 43\% & 7\\
C & 39\% & 7\\
''' + (r'D & 42\% & 7\\' if revised else '') + r'''
\bottomrule\end{tabular}
\end{table}
\end{document}
'''


if __name__ == '__main__':
    public=Path(__file__).resolve().parent/'public-demo'
    public.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='reportlens-public-latex-') as temp:
        root=Path(temp); repo=root/'report';repo.mkdir()
        def git(*args):
            subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True)
        git('init','-b','main');git('config','user.name','ReportLens demo');git('config','user.email','demo@example.invalid')
        for revised,name in ((False,'before'),(True,'after')):
            text=source(revised)
            (repo/'report.tex').write_text(text,encoding='utf-8')
            (public/f'latex-{name}.tex').write_text(text,encoding='utf-8')
            git('add','report.tex');git('commit','-m',f'Garden report {name}')
        service=Service(root/'output',Config(str(repo),output_directory=str(root/'output')))
        service.update=lambda message:print(message,flush=True)
        service.compare_git()
        for extension in ('pdf','reportlens'):
            artifact=next((root/'output').glob('*.'+extension))
            shutil.copyfile(artifact,public/f'latex-review.{extension}')
    print(public/'latex-review.pdf')
