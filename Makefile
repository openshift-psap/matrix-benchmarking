all:: benchmark.html
	./benchmark

benchmark.html: benchmark.md Makefile
	markdown -o $@ $<
