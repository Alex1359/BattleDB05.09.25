// Общие функции для работы с формами
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация всех элементов с data-toggle="tooltip"
    $('[data-toggle="tooltip"]').tooltip();
    
    // Подтверждение удаления
    $('.confirm-delete').on('click', function() {
        return confirm('Вы уверены, что хотите удалить эту запись?');
    });
    
    // Динамическое добавление полей
    $('.add-fields').on('click', function(e) {
        e.preventDefault();
        const container = $(this).data('container');
        const template = $(this).data('template');
        const newField = $(template).clone();
        $(container).append(newField);
        newField.find('input, select').val('');
        newField.find('.remove-fields').on('click', function() {
            $(this).closest('.field-group').remove();
        });
    });
    
    // Удаление полей
    $(document).on('click', '.remove-fields', function() {
        $(this).closest('.field-group').remove();
    });
});