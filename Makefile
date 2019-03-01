all:: benchmark.html
	./benchmark

benchmark.html: benchmark.txt Makefile
	asciidoc -n -a icons -a toc -o $@ $<
