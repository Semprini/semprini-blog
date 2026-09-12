/* Puts "Diagram" in the rich text toolbar and wires it to the snippet chooser.
 *
 * puput entries are Draftail rich text, not StreamFields, so this is the only
 * way a diagram reaches one. Only the id is stored: everything else about a
 * diagram lives on the snippet, so the body cannot carry anything of its own.
 */
(function () {
    'use strict';

    var React = window.React;
    var DraftJS = window.DraftJS;
    var draftail = window.draftail;
    if (!React || !DraftJS || !draftail) return;

    /* What the editor shows where the diagram sits. Deliberately a chip rather
       than a live preview: the diagram is inlined SVG with its own <style>, and
       dropping that into the editor would leak its rules into the admin. */
    function DiagramBlock(props) {
        var data = props.contentState.getEntity(props.entityKey).getData();
        return React.createElement(
            'div',
            { className: 'diagram-embed', role: 'img' },
            React.createElement('span', { className: 'diagram-embed__icon', 'aria-hidden': 'true' }, '▩'),
            React.createElement('span', { className: 'diagram-embed__label' },
                data.title || 'Diagram ' + data.id)
        );
    }

    function DiagramSource(props) {
        React.useEffect(function () {
            var editorState = props.editorState;
            var onComplete = props.onComplete;
            var onClose = props.onClose;

            window.ModalWorkflow({
                url: window.chooserUrls.diagramChooser,
                onload: window.CHOOSER_MODAL_ONLOAD_HANDLERS,
                responses: {
                    chosen: function (data) {
                        var content = editorState.getCurrentContent().createEntity(
                            'DIAGRAM', 'IMMUTABLE', { id: data.id, title: data.string }
                        );
                        var key = content.getLastCreatedEntityKey();
                        var withEntity = DraftJS.EditorState.set(editorState, { currentContent: content });
                        onComplete(DraftJS.AtomicBlockUtils.insertAtomicBlock(withEntity, key, ' '));
                    }
                },
                onError: function () { onClose(); }
            });
        }, []);
        return null;
    }

    draftail.registerPlugin(
        { type: 'DIAGRAM', source: DiagramSource, block: DiagramBlock },
        'entityTypes'
    );
})();
