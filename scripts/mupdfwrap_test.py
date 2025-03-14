#!/usr/bin/env python3

'''
Simple tests of the Python MuPDF API.
'''

import inspect
import os
import platform
import sys

if os.environ.get('MUPDF_PYTHON') in ('swig', None):
    # PYTHONPATH should have been set up to point to a build/shared-*/
    # directory containing mupdf.so generated by scripts/mupdfwrap.py and SWIG.
    import mupdf
elif os.environ.get('MUPDF_PYTHON') == 'cppyy':
    sys.path.insert(0, os.path.abspath(f'{__file__}/../../platform/python'))
    import mupdf_cppyy
    del sys.path[0]
    mupdf = mupdf_cppyy.cppyy.gbl.mupdf
else:
    raise Exception(f'Unrecognised $MUPDF_PYTHON: {os.environ.get("MUPDF_PYTHON")}')


_log_prefix = ''

def log(text):
    f = inspect.stack()[1]
    print(f'{f.filename}:{f.lineno} {_log_prefix}{text}', file=sys.stderr)
    sys.stderr.flush()

def log_prefix_set(prefix):
    global _log_prefix
    _log_prefix = prefix

g_test_n = 0

g_mupdf_root = os.path.abspath('%s/../..' % __file__)


def show_stext(document):
    '''
    Shows all available information about Stext blocks, lines and characters.
    '''
    for p in range(document.count_pages()):
        page = document.load_page(p)
        stextpage = mupdf.StextPage(page, mupdf.StextOptions())
        for block in stextpage:
            block_ = block.m_internal
            log(f'block: type={block_.type} bbox={block_.bbox}')
            for line in block:
                line_ = line.m_internal
                log(f'    line: wmode={line_.wmode}'
                        + f' dir={line_.dir}'
                        + f' bbox={line_.bbox}'
                        )
                for char in line:
                    char_ = char.m_internal
                    log(f'        char: {chr(char_.c)!r} c={char_.c:4} color={char_.color}'
                            + f' origin={char_.origin}'
                            + f' quad={char_.quad}'
                            + f' size={char_.size:6.2f}'
                            + f' font=('
                                +  f'is_mono={char_.font.flags.is_mono}'
                                + f' is_bold={char_.font.flags.is_bold}'
                                + f' is_italic={char_.font.flags.is_italic}'
                                + f' ft_substitute={char_.font.flags.ft_substitute}'
                                + f' ft_stretch={char_.font.flags.ft_stretch}'
                                + f' fake_bold={char_.font.flags.fake_bold}'
                                + f' fake_italic={char_.font.flags.fake_italic}'
                                + f' has_opentype={char_.font.flags.has_opentype}'
                                + f' invalid_bbox={char_.font.flags.invalid_bbox}'
                                + f' name={char_.font.name}'
                                + f')'
                            )


def test_filter(path):
    if platform.system() == 'Windows':
        print( 'Not testing mupdf.PdfFilterOptions2 because known to fail on Windows.')
        return

    # pdf_sanitizer_filter_options.
    class MySanitizeFilterOptions( mupdf.PdfSanitizeFilterOptions2):
        def __init__( self):
            super().__init__()
            self.use_virtual_text_filter()
            self.state = 1
        def text_filter( self, ctx, ucsbuf, ucslen, trm, ctm, bbox):
            if 0:
                log( f'text_filter(): ctx={ctx} ucsbuf={ucsbuf} ucslen={ucslen} trm={trm} ctm={ctm} bbox={bbox}')
            # Remove every other item.
            self.state = 1 - self.state
            return self.state
    sanitize_filter_options = MySanitizeFilterOptions()

    # pdf_filter_factory.
    class MyPdfFilterFactory( mupdf.PdfFilterFactory2):
        def __init__( self, sopts):
            super().__init__()
            self.sopts = sopts
            self.use_virtual_filter()
        def filter(self, ctx, doc, chain, struct_parents, transform, options):
            return mupdf.ll_pdf_new_sanitize_filter( doc, chain, struct_parents, transform, options, self.sopts)
        def filter_bad(self, ctx, doc, chain, struct_parents, transform, options, extra_arg):
            return mupdf.ll_pdf_new_sanitize_filter( doc, chain, struct_parents, transform, options, self.sopts)
    filter_factory = MyPdfFilterFactory( sanitize_filter_options.internal())

    # pdf_filter_options.
    class MyFilterOptions( mupdf.PdfFilterOptions2):
        def __init__( self):
            super().__init__()
            self.recurse = 1
            self.instance_forms = 0
            self.ascii = 1
    filter_options = MyFilterOptions()

    filter_options.add_factory( filter_factory.internal())

    document = mupdf.PdfDocument(path)
    for p in range(document.pdf_count_pages()):
        page = document.pdf_load_page(p)
        log( f'Running document.pdf_filter_page_contents on page {p}')
        document.pdf_begin_operation('test filter')
        document.pdf_filter_page_contents(page, filter_options)
        document.pdf_end_operation()

    if 1:
        # Try again but with a broken filter_factory callback method, and check
        # we get an appropriate exception. This checks that the SWIG Director
        # exception-handling code is working.
        #
        filter_factory.filter = filter_factory.filter_bad
        page = document.pdf_load_page(0)
        document.pdf_begin_operation('test filter')
        try:
            document.pdf_filter_page_contents(page, filter_options)
        except Exception as e:
            e_expected_text = "filter_bad() missing 1 required positional argument: 'extra_arg'"
            if e_expected_text not in str(e):
                raise Exception(f'Error does not contain expected text: {e_expected_text}') from e
        finally:
            document.pdf_end_operation()

    if 1:
        document.pdf_save_document('mupdf_test-out0.pdf', mupdf.PdfWriteOptions())


def test_install_load_system_font(path):
    '''
    Very basic test of mupdf.fz_install_load_system_font_funcs(). We check
    that the fonts returned by our python callback is returned if we ask for a
    non-existent font.

    We also render `path` as a PNG with/without our font override. This isn't
    particularly useful, but if `path` contained references to unknown fonts,
    it would give different results.
    '''
    print(f'test_install_load_system_font()')

    def make_png(infix=''):
        document = mupdf.FzDocument(path)
        pixmap = mupdf.FzPixmap(document, 0, mupdf.FzMatrix(), mupdf.FzColorspace(mupdf.FzColorspace.Fixed_RGB), 0)
        path_out = f'{path}{infix}.png'
        pixmap.fz_save_pixmap_as_png(path_out)
        print(f'Have created: {path_out}.')

    make_png()

    trace = list()
    replacement_font = mupdf.fz_new_font_from_file(
            None,
            os.path.abspath(f'{__file__}/../../resources/fonts/urw/NimbusRoman-BoldItalic.cff'),
            0,
            0,
            )
    assert replacement_font.m_internal
    print(f'{replacement_font.m_internal.name=} {replacement_font.m_internal.glyph_count=}')

    def font_f(name, bold, italic, needs_exact_metrics):
        trace.append((name, bold, italic, needs_exact_metrics))
        print(f'font_f(): Looking for font: {name=} {bold=} {italic=} {needs_exact_metrics=}.')
        # Always return `replacement_font`.
        return replacement_font
    def f_cjk(name, ordering, serif):
        trace.append((name, ordering, serif))
        print(f'f_cjk(): Looking for font: {name=} {ordering=} {serif=}.')
        return None
    def f_fallback(script, language, serif, bold, italic):
        trace.append((script, language, serif, bold, italic))
        print(f'f_fallback(): looking for font: {script=} {language=} {serif=} {bold=} {italic=}.')
        return None
    mupdf.fz_install_load_system_font_funcs(font_f, f_cjk, f_fallback)

    # Check that asking for any font returns `replacement_font`.
    font = mupdf.fz_load_system_font("some-font-name", 0, 0, 0)
    assert isinstance(font, mupdf.FzFont)
    assert trace == [
            ('some-font-name', 0, 0, 0),
            ], f'Incorrect {trace=}.'
    assert font.m_internal
    print(f'{font.m_internal.name=} {font.m_internal.glyph_count=}')
    assert font.m_internal.name == replacement_font.m_internal.name
    assert font.m_internal.glyph_count == replacement_font.m_internal.glyph_count

    make_png('-replace-font')

    # Restore default behaviour.
    mupdf.fz_install_load_system_font_funcs()
    font = mupdf.fz_load_system_font("some-font-name", 0, 0, 0)
    assert not font.m_internal


def test_barcode():
    # This should either succeed or raise an expected exception.
    try:
        pixmap = mupdf.fz_new_barcode_pixmap(
                mupdf.FZ_BARCODE_QRCODE, "http://artifex.com",
                size=512,
                ec_level=4,
                quiet=0,
                hrt=1,
                )
    except Exception as e:
        assert 'Barcode functionality not included' in str(e)


def test(path):
    '''
    Runs various mupdf operations on <path>, which is assumed to be a file that
    mupdf can open.
    '''
    log(f'testing path={path}')

    assert os.path.isfile(path)
    global g_test_n
    g_test_n += 1

    test_install_load_system_font(path)

    test_barcode()

    # See notes in wrap/swig.py:build_swig() about buffer_extract() and
    # buffer_storage().
    #
    assert getattr(mupdf.FzBuffer, 'fz_buffer_storage_raw', None) is None
    assert getattr(mupdf.FzBuffer, 'fz_buffer_storage')
    assert getattr(mupdf.FzBuffer, 'fz_buffer_extract')
    assert getattr(mupdf.FzBuffer, 'fz_buffer_extract_copy')

    # Test that we get the expected Python exception instance and text.
    document = mupdf.FzDocument(path)
    try:
        mupdf.fz_load_page(document, 99999999)
    except mupdf.FzErrorArgument as e:
        log(f'{type(e)=} {str(e)=} {repr(e)=}.')
        log(f'{e.what()=}.')
        expected = 'code=4: invalid page number: 100000000'
        assert str(e) == expected and e.what() == expected, (
                f'Incorrect exception text:\n'
                f'    {str(e)=}\n'
                f'    {e.what()=}\n'
                f'    {expected=}'
                )
    except Exception as e:
        assert 0, f'Incorrect exception {type(e)=} {e=}.'
    else:
        assert 0, f'No expected exception.'

    # Test SWIG Director wrapping of pdf_filter_options:
    #
    test_filter(path)

    # Test operations using functions:
    #
    log('Testing functions.')
    log(f'    Opening: %s' % path)
    document = mupdf.fz_open_document(path)
    log(f'    mupdf.fz_needs_password(document)={mupdf.fz_needs_password(document)}')
    log(f'    mupdf.fz_count_pages(document)={mupdf.fz_count_pages(document)}')
    log(f'    mupdf.fz_document_output_intent(document)={mupdf.fz_document_output_intent(document)}')

    # Test operations using classes:
    #
    log(f'Testing classes')

    document = mupdf.FzDocument(path)
    log(f'Have created mupdf.FzDocument for {path}')
    log(f'document.fz_needs_password()={document.fz_needs_password()}')
    log(f'document.fz_count_pages()={document.fz_count_pages()}')

    if 0:
        log(f'stext info:')
        show_stext(document)

    for k in (
            'format',
            'encryption',
            'info:Author',
            'info:Title',
            'info:Creator',
            'info:Producer',
            'qwerty',
            ):
        v = document.fz_lookup_metadata(k)
        log(f'document.fz_lookup_metadata() k={k} returned v={v!r}')
        if k == 'qwerty':
            assert v is None, f'v={v!r}'
        else:
            pass

    zoom = 10
    scale = mupdf.FzMatrix.fz_scale(zoom/100., zoom/100.)
    page_number = 0
    log(f'Have created scale: a={scale.a} b={scale.b} c={scale.c} d={scale.d} e={scale.e} f={scale.f}')

    colorspace = mupdf.FzColorspace(mupdf.FzColorspace.Fixed_RGB)
    log(f'colorspace.m_internal.key_storable.storable.refs={colorspace.m_internal.key_storable.storable.refs!r}')
    if 0:
        c = colorspace.fz_clamp_color([3.14])
        log('colorspace.clamp_color returned c={c}')
    pixmap = mupdf.FzPixmap(document, page_number, scale, colorspace, 0)
    log(f'Have created pixmap: {pixmap.m_internal.w} {pixmap.m_internal.h} {pixmap.m_internal.stride} {pixmap.m_internal.n}')

    filename = f'mupdf_test-out1-{g_test_n}.png'
    pixmap.fz_save_pixmap_as_png(filename)
    log(f'Have created {filename} using pixmap.save_pixmap_as_png().')

    # Print image data in ascii PPM format. Copied from
    # mupdf/docs/examples/example.c.
    #
    samples = pixmap.samples()
    stride = pixmap.stride()
    n = pixmap.n()
    filename = f'mupdf_test-out2-{g_test_n}.ppm'
    with open(filename, 'w') as f:
        f.write('P3\n')
        f.write('%s %s\n' % (pixmap.m_internal.w, pixmap.m_internal.h))
        f.write('255\n')
        for y in range(0, pixmap.m_internal.h):
            for x in range(pixmap.m_internal.w):
                if x:
                    f.write('  ')
                offset = y * stride + x * n
                if hasattr(mupdf, 'bytes_getitem'):
                    # swig
                    f.write('%3d %3d %3d' % (
                            mupdf.bytes_getitem(samples, offset + 0),
                            mupdf.bytes_getitem(samples, offset + 1),
                            mupdf.bytes_getitem(samples, offset + 2),
                            ))
                else:
                    # cppyy
                    f.write('%3d %3d %3d' % (
                            samples[offset + 0],
                            samples[offset + 1],
                            samples[offset + 2],
                            ))
            f.write('\n')
    log(f'Have created {filename} by scanning pixmap.')

    # Generate .png and but create Pixmap from Page instead of from Document.
    #
    page = mupdf.FzPage(document, 0)
    separations = page.fz_page_separations()
    log(f'page_separations() returned {"true" if separations else "false"}')
    pixmap = mupdf.FzPixmap(page, scale, colorspace, 0)
    filename = f'mupdf_test-out3-{g_test_n}.png'
    pixmap.fz_save_pixmap_as_png(filename)
    log(f'Have created {filename} using pixmap.fz_save_pixmap_as_png()')

    # Show links
    log(f'Links.')
    page = mupdf.FzPage(document, 0)
    link = mupdf.fz_load_links(page);
    log(f'{link}')
    if link:
        for i in link:
            log(f'{i}')

    # Check we can iterate over Link's, by creating one manually.
    #
    link = mupdf.FzLink(mupdf.FzRect(0, 0, 1, 1), "hello")
    log(f'items in <link> are:')
    for i in link:
        log(f'    {i.m_internal.refs} {i.m_internal.uri}')

    # Check iteration over Outlines. We do depth-first iteration.
    #
    log(f'Outlines.')
    def olog(text):
        if 0:
            log(text)
    num_outline_items = 0
    depth = 0
    it = mupdf.FzOutlineIterator(document)
    while 1:
        item = it.fz_outline_iterator_item()
        olog(f'depth={depth} valid={item.valid()}')
        if item.valid():
            log(f'{" "*depth*4}uri={item.uri()} is_open={item.is_open()} title={item.title()}')
            num_outline_items += 1
        else:
            olog(f'{" "*depth*4}<null>')
        r = it.fz_outline_iterator_down()
        olog(f'depth={depth} down => {r}')
        if r >= 0:
            depth += 1
        if r < 0:
            r = it.fz_outline_iterator_next()
            olog(f'depth={depth} next => {r}')
            assert r
            if r:
                # No more items at current depth, so repeatedly go up until we
                # can go right.
                end = 0
                while 1:
                    r = it.fz_outline_iterator_up()
                    olog(f'depth={depth} up => {r}')
                    if r < 0:
                        # We are at EOF. Need to break out of top-level loop.
                        end = 1
                        break
                    depth -= 1
                    r = it.fz_outline_iterator_next()
                    olog(f'depth={depth} next => {r}')
                    if r == 0:
                        # There are items at this level.
                        break
                if end:
                    break
    log(f'num_outline_items={num_outline_items}')

    # Check iteration over StextPage.
    #
    log(f'StextPage.')
    stext_options = mupdf.FzStextOptions(0)
    page_num = 40
    try:
        stext_page = mupdf.FzStextPage(document, page_num, stext_options)
    except Exception:
        log(f'no page_num={page_num}')
    else:
        device_stext = mupdf.FzDevice(stext_page, stext_options)
        matrix = mupdf.FzMatrix()
        page = mupdf.FzPage(document, 0)
        cookie = mupdf.FzCookie()
        page.fz_run_page(device_stext, matrix, cookie)
        log(f'    stext_page is:')
        for block in stext_page:
            log(f'        block:')
            for line in block:
                line_text = ''
                for char in line:
                    line_text += chr(char.m_internal.c)
                log(f'            {line_text}')

        device_stext.fz_close_device()

    # Check fz_search_page2().
    items = mupdf.fz_search_page2(document, 0, "compression", 20)
    print(f'{len(items)=}')
    for item in items:
        print(f'    {item.mark=} {item.quad=}')

    # Check copy-constructor.
    log(f'Checking copy-constructor')
    document2 = mupdf.FzDocument(document)
    del document
    page = mupdf.FzPage(document2, 0)
    scale = mupdf.FzMatrix()
    pixmap = mupdf.FzPixmap(page, scale, colorspace, 0)
    pixmap.fz_save_pixmap_as_png('mupdf_test-out3.png')

    stdout = mupdf.FzOutput(mupdf.FzOutput.Fixed_STDOUT)
    log(f'{type(stdout)} {stdout.m_internal.state}')

    mediabox = page.fz_bound_page()
    out = mupdf.FzDocumentWriter(filename, 'png', '', mupdf.FzDocumentWriter.FormatPathType_DOCUMENT)
    dev = out.fz_begin_page(mediabox)
    page.fz_run_page(dev, mupdf.FzMatrix(mupdf.fz_identity), mupdf.FzCookie())
    out.fz_end_page()

    # Check out-params are converted into python return value.
    bitmap = mupdf.FzBitmap(10, 20, 8, 72, 72)
    bitmap_details = bitmap.fz_bitmap_details()
    log(f'{bitmap_details}')
    assert list(bitmap_details) == [10, 20, 8, 12], f'bitmap_details={bitmap_details!r}'

    log(f'finished test of %s' % path)


if __name__ == '__main__':

    print(f'{mupdf.Py_LIMITED_API=}', flush=1)
    paths = sys.argv[1:]
    if not paths:
        paths = [
                f'{g_mupdf_root}/thirdparty/zlib/zlib.3.pdf',
                ]
    # Run test() on all the .pdf files in the mupdf repository.
    #
    for path in paths:

        log_prefix_set(f'{os.path.relpath(path, g_mupdf_root)}: ')
        try:
            test(path)
        finally:
            log_prefix_set('')

    log(f'finished')
